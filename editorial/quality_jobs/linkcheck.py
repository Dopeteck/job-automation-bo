from __future__ import annotations

from urllib.parse import urlsplit

import requests


def check_link(url: str, *, timeout: int, user_agent: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return "invalid"
    headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"}
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout, headers=headers)
        if response.status_code in {405, 501}:
            response = requests.get(
                url,
                allow_redirects=True,
                timeout=timeout,
                headers={**headers, "Range": "bytes=0-2048"},
                stream=True,
            )
        code = response.status_code
        if code in {404, 410}:
            return str(code)
        if code in {401, 403, 429}:
            return "protected"
        if 300 <= code < 400 or response.history:
            return "redirect"
        if 200 <= code < 300:
            return "200"
        if code >= 500:
            return "temporary_error"
        return str(code)
    except requests.RequestException:
        return "unreachable"

