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
