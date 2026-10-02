"""youtube_search tool.

Searches YouTube for real, currently-public videos via the official
YouTube Data API v3 -- a real REST call, mirroring web_search.py's design
exactly: no mock mode, YOUTUBE_API_KEY required via settings.require()
(raises MissingConfigurationError immediately if it isn't set, same as
every other credentialed tool in this project), and a genuine transient
failure (network blip, timeout, a real quota-exhausted 4xx/5xx from
Google) logs and returns an empty list rather than raising -- FR-14, one
source outage never crashes the daily run.

This only finds videos and their metadata (title, channel, publish date,
description snippet) -- it does not read what's actually said in the
video. See youtube_transcript.py for that half; the two are used together
by the YouTube agent in src/agents/monitoring_agent.py, the same
search-then-fetch shape as the web agents' web_search() + fetch_page().

The API itself is free (no billing account required for this usage level)
-- see .env.example for how to get a key. Quota is unit-based rather than
dollar-based: a search.list call costs 100 of the default 10,000
units/day, so this tool comfortably supports far more than the one call/
day the daily digest actually makes.
"""
from __future__ import annotations

import datetime as dt
import html
import logging
from typing import Optional

import httpx
from pydantic import BaseModel

from src.config import settings

logger = logging.getLogger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class VideoResult(BaseModel):
    video_id: str
    title: str
    channel_title: str
    description: str
    published_date: Optional[str] = None

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


def youtube_search(
    query: str,
    max_results: int = 5,
    recency_days: Optional[int] = None,
    region_code: Optional[str] = None,
) -> list[VideoResult]:
    """Query YouTube for real, public videos matching `query`.

    `recency_days`, when set, restricts to videos published in the last N
    days via the API's publishedAfter parameter -- the same idea as
    web_search()'s recency_days for Tavily's news mode: a five-year-old
    video isn't a "today" event for a daily intelligence digest.

    `region_code` (ISO 3166-1 alpha-2, e.g. "MA") biases results toward
    what's viewable/relevant in that country when set; left unset (None)
    by default here since it has not been verified against the real API in
    a session with a real key -- worth testing once YOUTUBE_API_KEY is
    configured, the same "verify against the real API, don't assume"
    standard the rest of this file's domain/recency choices were held to.
    """
    api_key = settings.require("youtube_api_key", "YOUTUBE_API_KEY")

    params: dict = {
        "key": api_key,
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": max_results,
        "order": "relevance",
        "safeSearch": "none",
    }
    if recency_days:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=recency_days)
        params["publishedAfter"] = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    if region_code:
        params["regionCode"] = region_code

    try:
        resp = httpx.get(YOUTUBE_SEARCH_URL, params=params, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        body = resp.json()
        results: list[VideoResult] = []
        for item in body.get("items", [])[:max_results]:
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            snippet = item.get("snippet", {})
            # 2026-09-21: a real live run showed a real video title coming
            # back as "...il n&#39;y a aucun avenir !" -- the YouTube Data
            # API returns title/channelTitle/description HTML-escaped, and
            # nothing downstream (the report, the web console, the PDF
            # export) unescapes it, so it would show up broken everywhere
            # this text is displayed, not just in a one-off test. Decode it
            # once, here, at the source.
            results.append(
                VideoResult(
                    video_id=video_id,
                    title=html.unescape(snippet.get("title", "")),
                    channel_title=html.unescape(snippet.get("channelTitle", "")),
                    description=html.unescape(snippet.get("description", "")),
                    published_date=snippet.get("publishedAt"),
                )
            )
        logger.info("youtube_search query=%r -> %d results", query, len(results))
        return results
    except httpx.HTTPStatusError as exc:
        # Google's error responses carry a JSON body with the *real* reason
        # (e.g. "accessNotConfigured" when the YouTube Data API v3 hasn't
        # been enabled for the project, "keyInvalid", or a quota reason) --
        # far more useful than the bare "403 Forbidden" the exception's
        # string form gives on its own. Best-effort: if the body isn't
        # JSON (or doesn't have this shape) fall back to the plain str().
        detail = str(exc)
        try:
            error_body = exc.response.json().get("error", {})
            reason = (error_body.get("errors") or [{}])[0].get("reason")
            message = error_body.get("message")
            if reason or message:
                detail = f"HTTP {exc.response.status_code}, reason={reason!r}, message={message!r}"
        except Exception:
            pass
        logger.error("youtube_search failed query=%r: %s", query, detail)
        return []
    except Exception as exc:
        logger.error("youtube_search failed query=%r: %s", query, exc)
        return []
