#!/usr/bin/env python3
"""
site_fetcher.py - Auto-fetch brand logo and home-banner image from a website.
"""

import re
import requests
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SEOSchemaBot/2.0)"}


def _base(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _get(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def _abs(base: str, href: str) -> str:
    return urljoin(base, href)


LOGO_PATTERNS = [
    r'"logo"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"',
    r'"logo"\s*:\s*"([^"]+)"',
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    r'<img[^>]+(?:class|id|alt)=["\'][^"\']*logo[^"\']*["\'][^>]+src=["\']([^"\']+)["\']',
    r'<img[^>]+src=["\']([^"\']+)["\'][^>]+(?:class|id|alt)=["\'][^"\']*logo[^"\']*["\']',
    r'<link[^>]+rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]+href=["\']([^"\']+)["\']',
]

BANNER_PATTERNS = [
    r'<(?:section|div)[^>]+(?:class|id)=["\'][^"\']*(?:hero|banner|slider)[^"\']*["\'][^>]*>.*?<img[^>]+src=["\']([^"\']+)["\']',
    r'(?:class|id)=["\'][^"\']*(?:hero|banner)[^"\']*["\'][^>]*style=["\'][^"\']*background(?:-image)?\s*:\s*url\(["\']?([^"\')\s]+)',
    r'<section[^>]*>(?:(?!<section).)*?<img[^>]+src=["\']([^"\']+)["\']',
]

# ── Social media domain patterns ──────────────────────────────────────────────
_SOCIAL_DOMAINS = [
    "facebook.com", "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "youtube.com", "pinterest.com", "threads.net",
]

# ── Phone number pattern ───────────────────────────────────────────────────────
_PHONE_RE = re.compile(
    r'(?:tel:|telephone["\']?\s*:\s*["\']?|phone["\']?\s*:\s*["\']?|'
    r'(?:call\s+us|contact|helpline|toll[\s-]?free)[^<]{0,40})'
    r'(\+?[\d][\d\s\-().]{7,20}\d)',
    re.I,
)


def fetch_logo(page_url: str) -> Optional[str]:
    base = _base(page_url)
    html = _get(base)
    if not html:
        return None
    for pat in LOGO_PATTERNS:
        m = re.search(pat, html, re.I | re.S)
        if m:
            url = m.group(1).strip()
            if not url.startswith("data:"):
                return _abs(base, url)
    return None


def fetch_banner(page_url: str) -> Optional[str]:
    base = _base(page_url)
    html = _get(base)
    if not html:
        return None
    for pat in BANNER_PATTERNS:
        m = re.search(pat, html, re.I | re.S)
        if m:
            url = m.group(1).strip()
            if not url.startswith("data:"):
                return _abs(base, url)
    return None


def fetch_site_assets(page_url: str) -> Tuple[Optional[str], Optional[str]]:
    return fetch_logo(page_url), fetch_banner(page_url)


# ── Organization-specific scrapers ────────────────────────────────────────────

def _extract_social_links(html: str) -> list:
    """Extract unique social media profile URLs from page HTML."""
    seen = set()
    links = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        href = href.strip().rstrip("/")
        if any(d in href for d in _SOCIAL_DOMAINS):
            # Only keep profile-level URLs (not share buttons)
            if href.startswith("http") and href not in seen:
                # Filter out generic share/sharer URLs
                if not re.search(r'sharer|share\?|intent/tweet|addtoany', href, re.I):
                    seen.add(href)
                    links.append(href)
    return links


def _extract_phone(html: str) -> Optional[str]:
    """Extract first phone number found near contact/footer context."""
    # Try structured tel: links first
    tel = re.search(r'href=["\']tel:([^"\']+)["\']', html, re.I)
    if tel:
        return tel.group(1).strip()
    # Fallback: pattern match
    m = _PHONE_RE.search(html)
    if m:
        return re.sub(r'\s+', '', m.group(1)).strip()
    return None


def _extract_meta_description(html: str) -> Optional[str]:
    """Extract meta description or og:description from HTML."""
    for pat in [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{10,})["\']',
        r'<meta[^>]+content=["\']([^"\']{10,})["\'][^>]+name=["\']description["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']{10,})["\']',
        r'<meta[^>]+content=["\']([^"\']{10,})["\'][^>]+property=["\']og:description["\']',
    ]:
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    return None


def fetch_org_data(page_url: str) -> dict:
    """
    Scrape organization-level data from a website:
      - logo_url       : brand logo
      - description    : meta/og description
      - same_as        : list of social media profile URLs
      - telephone      : first phone number found on the page
    """
    base = _base(page_url)

    # 1. Fetch homepage HTML
    home_html = _get(base) or ""

    logo_url = None
    for pat in LOGO_PATTERNS:
        m = re.search(pat, home_html, re.I | re.S)
        if m:
            u = m.group(1).strip()
            if not u.startswith("data:"):
                logo_url = _abs(base, u)
                break

    description = _extract_meta_description(home_html)
    same_as     = _extract_social_links(home_html)
    telephone   = _extract_phone(home_html)

    # 2. If no phone on homepage, try /contact-us, /contact, /about-us
    if not telephone:
        for slug in ("/contact-us", "/contact", "/about-us", "/about"):
            contact_html = _get(base + slug) or ""
            if contact_html:
                telephone = _extract_phone(contact_html)
                # Also pick up any extra social links
                for lnk in _extract_social_links(contact_html):
                    if lnk not in same_as:
                        same_as.append(lnk)
                if telephone:
                    break

    return {
        "logo_url":    logo_url,
        "description": description,
        "same_as":     same_as,
        "telephone":   telephone,
    }
