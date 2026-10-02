"""fetch_page tool — retrieve raw HTML for a URL.

No mock mode: this always does a real HTTP GET. Returns None on a genuine
fetch failure (bad URL, non-HTML content, network error) rather than
raising — that's an honest "couldn't retrieve this one page," not
fabrication, and matches the tool-design principle used throughout this
project (one bad URL shouldn't crash the whole agent run).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from pydantic import BaseModel

from src.config import settings

logger = logging.getLogger(__name__)

_MAX_CONTENT_LENGTH = 2_000_000  # security cap, see docs/20_security_and_limitations.md pattern


class RawPage(BaseModel):
    url: str
    html: str


def fetch_page(url: str, timeout_s: Optional[int] = None) -> Optional[RawPage]:
    try:
        resp = httpx.get(url, timeout=timeout_s or settings.request_timeout_seconds, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type:
            logger.warning("fetch_page rejected non-HTML content-type=%s url=%s", content_type, url)
            return None
        html = resp.text[:_MAX_CONTENT_LENGTH]
        return RawPage(url=url, html=html)
    except Exception as exc:
        logger.warning("fetch_page failed url=%s: %s", url, exc)
        return None
