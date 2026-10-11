from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup


TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def clean_text(value: str | None, limit: int = 800) -> str:
    # Some feeds entity-encode their HTML more than once.
    unescaped = html.unescape(html.unescape(value or ""))
    text = BeautifulSoup(unescaped, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def fingerprint(title: str, company: str) -> str:
    def normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    material = f"{normalize(title)}|{normalize(company)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def safe_html(value: str) -> str:
    return html.escape(value or "", quote=True)


def shorten(value: str, length: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= length:
        return value
    return value[: max(0, length - 1)].rstrip() + "…"
