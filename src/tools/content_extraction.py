"""extract_content tool — turn raw HTML into clean article text.

This is a pure, deterministic HTML -> text transform with no external
dependency and no credential of its own — it runs the same way regardless
of what fetched the HTML it's given. Uses the standard-library html.parser
so the project has no hard dependency on a third-party extraction library
for the MVP; swap in trafilatura later (see docs/13_technology_stack.md
pattern) if extraction quality on real pages needs improving.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Optional

from pydantic import BaseModel


class ExtractedContent(BaseModel):
    title: str
    main_text: str
    detected_publish_date: Optional[str] = None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []
        self.title_chunks: list[str] = []
        self._in_title = False
        self._skip_tags = {"script", "style"}
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip_depth += 1
        if tag == "title" or tag == "h1":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "title" or tag == "h1":
            self._in_title = False

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_chunks.append(text)
        self.chunks.append(text)


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def extract_content(raw_html: str) -> ExtractedContent:
    parser = _TextExtractor()
    parser.feed(raw_html)
    title = parser.title_chunks[0] if parser.title_chunks else ""
    main_text = " ".join(parser.chunks)
    date_match = _DATE_RE.search(main_text)
    return ExtractedContent(
        title=title,
        main_text=main_text,
        detected_publish_date=date_match.group(0) if date_match else None,
    )
