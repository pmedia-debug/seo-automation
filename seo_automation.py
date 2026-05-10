#!/usr/bin/env python3
"""
seo_automation.py - Schema builder.

Accepts parsed doc_data dict and builds all JSON-LD schema blocks.

Schema generation rules:
  - Breadcrumb schema : ALWAYS generated for every URL
  - FAQ schema        : ALWAYS generated when FAQs are found in the doc
  - Product schema    : ONLY when schema_type == "product"
  - Blog/Article schema: ONLY when schema_type == "blog"
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug_to_title(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.replace("-", " ").split())


def get_brand(url: str) -> str:
    parsed = urlparse(url)
    host   = parsed.netloc.lower().lstrip("www.")
    label  = host.split(".")[0] if host else "Brand"
    return label.replace("-", " ").title()


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    limit   = max_len - 3
    trimmed = text[:limit].rstrip()
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0]
    return trimmed + "..."


def _wrap(data: Dict) -> str:
    return (
        '<script type="application/ld+json">\n'
        + json.dumps(data, indent=2, ensure_ascii=False)
        + "\n</script>"
    )


# ── Meta tags ─────────────────────────────────────────────────────────────────

def build_meta_title(h1: str, site_name: Optional[str] = None) -> str:
    base = h1.strip()
    if site_name:
        candidate = f"{base} | {site_name.strip()}"
        if len(candidate) <= 60:
            return candidate
    return _truncate(base, 60)


def build_meta_description(provided: Optional[str], h1: str) -> str:
    raw = provided.strip() if provided and provided.strip() else (
        f"Learn all about {h1} and how it can benefit you."
    )
    return _truncate(raw, 160)


# ── Breadcrumb schema ─────────────────────────────────────────────────────────

def build_breadcrumb_schema(url: str) -> str:
    parsed  = urlparse(url)
    base    = f"{parsed.scheme}://{parsed.netloc}/"
    segs    = [s for s in parsed.path.split("/") if s]
    items   = [{"@type": "ListItem", "position": 1, "name": "Home", "item": base}]
    current = f"{parsed.scheme}://{parsed.netloc}"
    for i, seg in enumerate(segs, 2):
        current += f"/{seg}"
        items.append({"@type": "ListItem", "position": i,
                      "name": slug_to_title(seg), "item": current})
    return _wrap({"@context": "https://schema.org",
                  "@type": "BreadcrumbList", "itemListElement": items})


# ── FAQ schema ────────────────────────────────────────────────────────────────

def build_faq_schema(faqs: List[Dict[str, str]]) -> str:
    if not faqs:
        return ""
    return _wrap({
        "@context":   "https://schema.org",
        "@type":      "FAQPage",
        "name":       "FAQs",
        "mainEntity": [
            {"@type": "Question", "name": f["q"],
             "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
            for f in faqs
        ],
    })


# ── Product schema ─────────────────────────────────────────────────────────────
def build_product_schema(
    *,
    product_name:  str,
    page_url:      str,
    image_url:     str,
    description:   str,
    brand_name:    str,
    logo_url:      Optional[str],
    rating_value:  Optional[str] = None,
    best_rating:   Optional[str] = None,
) -> str:

    data: Dict[str, Any] = {
        "@context":    "[schema.org](https://schema.org)",
        "@type":       "Product",
        "name":        product_name,
        "url":         page_url,
        "image":       image_url,
        "description": description,
        "brand": {
            "@type": "Brand",
            "name":  brand_name,
        },
        "provider": {
            "@type": "Organization",
            "name":  brand_name,   # ← always auto-filled from brand, no doc input needed
        },
    }

    # aggregateRating only emitted when ratingValue is present in doc
    if rating_value:
        data["aggregateRating"] = {
            "@type":       "AggregateRating",
            "ratingValue": rating_value,
            "bestRating":  best_rating or "5",
        }

    return _wrap(data)


# ── Blog / Article schema ─────────────────────────────────────────────────────

def build_blog_schema(
    *, page_url: str, headline: str, description: str, image_url: str,
    publisher_name: str, logo_url: Optional[str], author_name: Optional[str] = None,
) -> str:
    now = _now_iso()
    return _wrap({
        "@context": "https://schema.org",
        "@type":    "Article",
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
        "headline":    headline,
        "description": description,
        "image":       image_url,
        "author":      {"@type": "Organization", "name": author_name or publisher_name},
        "publisher": {
            "@type": "Organization",
            "name":  publisher_name,
            "logo":  {"@type": "ImageObject", "url": logo_url or ""},
        },
        "datePublished": now,
        "dateModified":  now,
    })


# ── Master builder ─────────────────────────────────────────────────────────────

def build_all_schemas(
    *, doc_data: Dict[str, Any], schema_type: str,
    logo_url: Optional[str], banner_url: Optional[str],
) -> Dict[str, str]:
    """
    schema_type : "none" | "product" | "blog"

    Always returns:
      - breadcrumb_schema  (every URL)
      - faq_schema         (when FAQs found in doc)

    Additionally returns when explicitly selected:
      - product_schema     (schema_type == "product")
      - blog_schema        (schema_type == "blog")

    So selecting Product gives:  breadcrumb + faq + product
    Selecting Blog gives:        breadcrumb + faq + blog
    Selecting None gives:        breadcrumb + faq only
    """
    page_url = doc_data.get("page_url") or ""

    h1 = doc_data.get("h1") or slug_to_title(
        urlparse(page_url).path.split("/")[-1] or "page"
    )

    product_name = doc_data.get("product_name") or h1
    faqs         = doc_data.get("faqs") or []
    image_url    = doc_data.get("image_url") or banner_url or ""
    brand        = get_brand(page_url) if page_url else "Brand"

    meta_desc  = build_meta_description(doc_data.get("meta_description"), h1)
    meta_title = build_meta_title(h1, brand)

    # ── Always generated ───────────────────────────────────────────────────
    breadcrumb = build_breadcrumb_schema(page_url) if page_url else ""
    faq        = build_faq_schema(faqs)

    result = {
        "meta_title":        meta_title,
        "meta_description":  meta_desc,
        "breadcrumb_schema": breadcrumb,
        "faq_schema":        faq,
        "product_schema":    "",
        "blog_schema":       "",
    }

    # ── Selective: only when explicitly requested ──────────────────────────
    if schema_type == "product":
    result["product_schema"] = build_product_schema(
        product_name = product_name,
        page_url     = page_url,
        image_url    = image_url,
        description  = meta_desc,
        brand_name   = brand,
        logo_url     = logo_url,
        rating_value = doc_data.get("rating_value"),
        best_rating  = doc_data.get("best_rating"),
    )

    elif schema_type == "blog":
        result["blog_schema"] = build_blog_schema(
            page_url       = page_url,
            headline       = h1,
            description    = meta_desc,
            image_url      = image_url,
            publisher_name = brand,
            logo_url       = logo_url,
        )

    # schema_type == "none" -> breadcrumb + faq only, nothing extra

    return result