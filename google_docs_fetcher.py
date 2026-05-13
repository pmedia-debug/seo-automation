#!/usr/bin/env python3
"""
google_docs_fetcher.py

Fetch SEO content from a Google Doc.

Auth priority:
  1. OAuth2 (token dict passed from Flask session) -> Google Docs API v1
  2. Public export URL fallback (docs shared as "Anyone with link")

FIX: H1/Headline/Heading labels in the doc are indicators for the tool only.
     The label itself is NEVER included in the extracted value.

     "H1 - Asus ROG Laptops"          ->  "Asus ROG Laptops"
     "Headline: Best Gaming Laptops"   ->  "Best Gaming Laptops"
     "Heading 1 - Today is Green Day"  ->  "Today is Green Day"
"""

import os
import re
import requests
from typing import Any, Dict, List, Optional

# ── Config ────────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]
CLIENT_SECRET_FILE = os.path.join(
    os.path.dirname(__file__),
    "client_secret_954256371489-n8thfglpupe95gljqnbh92n1ueeno08d.apps.googleusercontent.com.json",
)

DRIVE_EXPORT_TXT  = "https://docs.google.com/document/d/{doc_id}/export?format=txt"
DRIVE_EXPORT_HTML = "https://docs.google.com/document/d/{doc_id}/export?format=html"
HEADERS = {"User-Agent": "SEOSchemaBot/2.0"}

# ── Label-stripping regex ─────────────────────────────────────────────────────
# Strips any known label prefix (H1, Headline, Heading, URL, etc.) + separator.
# These are doc indicators only — the clean value after them is what we want.
_LABEL_STRIP_RE = re.compile(
    r"^(?:h1\s*tag|h1|heading\s*1|heading|headline"
    r"|page\s*url|url|meta\s*desc(?:ription)?|description"
    r"|product\s*name|product|image(?:\s*url|\s*link)?"
    r"|brand\s*name|site\s*name|publisher\s*name"
    r"|rating\s*value|ratingvalue|best\s*rating|bestrating"
    r"|rating\s*count|ratingcount"
    r")\s*[:-]\s*",
    re.I,
)

# ─────────────────────────────────────────────────────────────────────────────

def extract_doc_id(docs_url: str) -> str:
    match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", docs_url)
    if not match:
        raise ValueError(
            "Could not find a document ID in: " + docs_url + "\n"
            "Please use a valid Google Docs share URL."
        )
    return match.group(1)

# ── OAuth2 helpers ─────────────────────────────────────────────────────────────

def credentials_to_dict(creds) -> Dict:
    return {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        list(creds.scopes) if creds.scopes else [],
    }

def credentials_from_dict(d: Dict):
    from google.oauth2.credentials import Credentials
    return Credentials(
        token         = d.get("token"),
        refresh_token = d.get("refresh_token"),
        token_uri     = d.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id     = d.get("client_id"),
        client_secret = d.get("client_secret"),
        scopes        = d.get("scopes"),
    )

def _refresh_if_needed(creds):
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
    return creds

# ── Docs API helpers (OAuth2 path) ─────────────────────────────────────────────

def _build_service(token_dict: Dict):
    from googleapiclient.discovery import build
    creds = credentials_from_dict(token_dict)
    creds = _refresh_if_needed(creds)
    return build("docs", "v1", credentials=creds)

def _para_text(paragraph: Dict) -> str:
    return "".join(
        e.get("textRun", {}).get("content", "")
        for e in paragraph.get("elements", [])
    ).strip()

def _inline_images(doc: Dict) -> List[str]:
    objs = doc.get("inlineObjects", {})
    urls = []

    def walk(elements):
        for e in elements:
            if "inlineObjectElement" in e:
                oid = e["inlineObjectElement"].get("inlineObjectId", "")
                uri = (objs.get(oid, {})
                       .get("inlineObjectProperties", {})
                       .get("embeddedObject", {})
                       .get("imageProperties", {})
                       .get("contentUri", ""))
                if uri:
                    urls.append(uri)
            if "table" in e:
                for row in e["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        walk(cell.get("content", []))

    for block in doc.get("body", {}).get("content", []):
        if "paragraph" in block:
            walk(block["paragraph"].get("elements", []))
        if "table" in block:
            for row in block["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    walk(cell.get("content", []))
    return urls

def _doc_to_lines(doc: Dict) -> List[str]:
    lines = []
    for block in doc.get("body", {}).get("content", []):
        if "paragraph" in block:
            t = _para_text(block["paragraph"])
            if t:
                lines.append(t)
    return lines

# ── Export URL helpers (fallback path) ────────────────────────────────────────

def _export_txt(doc_id: str) -> str:
    r = requests.get(DRIVE_EXPORT_TXT.format(doc_id=doc_id),
                     headers=HEADERS, timeout=25, allow_redirects=True)
    if r.status_code == 403:
        raise ValueError(
            "This Google Doc is private.\n"
            "Connect your Google account using the button above, "
            "or set the doc sharing to 'Anyone with the link can view'."
        )
    r.raise_for_status()
    return r.text

def _export_html(doc_id: str) -> str:
    try:
        r = requests.get(DRIVE_EXPORT_HTML.format(doc_id=doc_id),
                         headers=HEADERS, timeout=25, allow_redirects=True)
        return r.text if r.status_code == 200 else ""
    except Exception:
        return ""

def _html_images(html: str) -> List[str]:
    return [
        m.group(1) for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
        if m.group(1).startswith("http") and "1x1" not in m.group(1)
    ]

# ── Field parsers ─────────────────────────────────────────────────────────────

def _strip_label(line: str) -> str:
    """
    Strip any known label prefix from a line and return only the clean value.

    "H1: Asus ROG Laptops"           ->  "Asus ROG Laptops"
    "H1 - Asus ROG Laptops"          ->  "Asus ROG Laptops"
    "Headline: Best Gaming Laptops"  ->  "Best Gaming Laptops"
    "Heading 1 - Today is Green Day" ->  "Today is Green Day"
    "Asus ROG Laptops"               ->  "Asus ROG Laptops"  (no label, unchanged)
    """
    return _LABEL_STRIP_RE.sub("", line.strip(), count=1).strip()


def _find_field(lines: List[str], *labels: str) -> Optional[str]:
    """
    Find a labeled field and return only the value — never the label itself.
    Matches: "Label: value"  or  "Label - value"
    """
    pat = re.compile(
        r"^(?:" + "|".join(re.escape(l) for l in labels) + r")\s*[:\-]\s*(.+)",
        re.I,
    )
    for line in lines:
        m = pat.match(line.strip())
        if m:
            return m.group(1).strip()
    return None


def _extract_faqs(lines: List[str]) -> List[Dict[str, str]]:
    """
    Extract Q&A pairs. Enters FAQ mode on any heading containing
    'faq', 'frequently asked', or 'common questions'.

    Supported Q/A formats:
        Q: ...  Q1: ...  Q.  Q1.  Q)  Q1)
        A: ...  A1: ...  A.  A1.  A)  A1)
    """
    faqs: List[Dict[str, str]] = []
    in_faq = False
    current_q: Optional[str] = None
    _faq_heading = re.compile(r"(faq|frequently\s+asked|common\s+questions?)", re.I)

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        cleaned = re.sub(r"['\"\-/\\|(){}[\]#*_]", " ", line)
        if _faq_heading.search(cleaned):
            in_faq = True
            current_q = None
            continue

        if not in_faq:
            continue

        q_match = re.match(r"^Q\d*\s*[:\.\)]\s*(.+)", line, re.I)
        a_match = re.match(r"^A\d*\s*[:\.\)]\s*(.+)", line, re.I)

        if q_match:
            current_q = q_match.group(1).strip()
        elif a_match and current_q:
            faqs.append({"q": current_q, "a": a_match.group(1).strip()})
            current_q = None

    return faqs


# Pure-label-only lines (no value after them) — skip these entirely
_PURE_LABEL_RE = re.compile(
    r"^(?:h1\s*tag|h1|heading\s*1|heading|headline"
    r"|page\s*url|url|meta\s*desc(?:ription)?|description"
    r"|product\s*name|product|image(?:\s*url|\s*link)?"
    r"|brand\s*name|site\s*name|publisher\s*name"
    r"|rating\s*value|ratingvalue|best\s*rating|bestrating"
    r"|rating\s*count|ratingcount"
    r")\s*$",
    re.I,
)


def _parse(lines: List[str], img_fallbacks: List[str]) -> Dict[str, Any]:
    img = _find_field(lines, "Image URL", "Image Url", "Image Link", "Image")
    if not img and img_fallbacks:
        img = img_fallbacks[0]

    # Try to find a labeled H1/Headline/Heading field first.
    # _find_field already returns only the value after the label separator.
    h1 = _find_field(lines, "H1", "H1 Tag", "Heading 1", "Heading", "Headline")

    if not h1:
        # No labeled field found — scan lines for first usable heading.
        # Apply _strip_label so even unlabeled lines like "H1 - My Title"
        # get the label stripped before being used.
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if _PURE_LABEL_RE.match(line):
                continue
            stripped = _strip_label(line)
            if stripped and len(stripped) < 200:
                h1 = stripped
                break

    return {
    "page_url":         _find_field(lines, "Page URL", "Page Url", "URL"),
    "meta_description": _find_field(lines, "Meta Description", "Meta Desc", "Description"),
    "h1":               h1,
    "product_name":     _find_field(lines, "Product Name", "Product"),
    "image_url":        img,
    "faqs":             _extract_faqs(lines),
    # ── fetched from doc for product schema ────────────────────────────
    "rating_value":     _find_field(lines, "Rating Value", "ratingValue"),
    "best_rating":      _find_field(lines, "Best Rating",  "bestRating"),
    "rating_count":     _find_field(lines, "Rating Count", "ratingCount"),
}


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_doc_data(docs_url: str, token_dict: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Fetch SEO fields from a Google Doc.

    token_dict: OAuth2 token from Flask session (use Docs API).
    None:       fall back to public export URL.
    """
    doc_id = extract_doc_id(docs_url)

    if token_dict:
        try:
            svc = _build_service(token_dict)
            doc = svc.documents().get(documentId=doc_id).execute()
            lines = _doc_to_lines(doc)
            imgs  = _inline_images(doc)
            out   = _parse(lines, imgs)
            out["_auth_mode"] = "oauth2"
            return out
        except Exception as exc:
            print(f"[SEOBot] Docs API failed ({exc}), trying export URL.")

    plain = _export_txt(doc_id)
    lines = [l for l in plain.splitlines() if l.strip()]
    html  = _export_html(doc_id)
    imgs  = _html_images(html)
    out   = _parse(lines, imgs)
    out["_auth_mode"] = "export_url"
    return out