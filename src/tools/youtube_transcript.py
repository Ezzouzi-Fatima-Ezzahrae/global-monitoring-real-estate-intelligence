"""fetch_transcript tool -- retrieve the real spoken-word transcript/caption
track for a YouTube video.

Uses youtube-transcript-api (see requirements.txt), a widely used Python
library that reads the same public caption track YouTube serves to any
viewer who clicks "Show transcript" in the player. It needs no API key of
its own -- distinct from youtube_search.py's YOUTUBE_API_KEY, which is the
official, documented Data API. This is not: it isn't a contractually
supported Google endpoint, so it can break if YouTube changes how captions
are served, and (like page_fetch.py's HTML fetch) it fails honestly, not
silently, when that happens rather than raising into the caller.

No mock mode, same as every other tool here: a genuine per-video failure
(captions disabled for that video, no transcript in a language we ask
for, video unavailable/private/removed since it was indexed) returns
None -- an honest "couldn't retrieve this one video's transcript" -- and
is logged, never fabricated. The calling agent (src/agents/
monitoring_agent.py) skips that one video and moves to the next, the same
way it already skips one unfetchable web page (FR-14).
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Tried in this order: Arabic and French first, since a meaningful share of
# what this system actually cares about (Morocco/MENA commentary) is
# published in those languages; English as the broadest fallback. The
# library falls through the list and uses whichever one is actually
# available for a given video.
_PREFERRED_LANGUAGES = ["ar", "fr", "en"]


class VideoTranscript(BaseModel):
    video_id: str
    text: str


def fetch_transcript(video_id: str) -> Optional[VideoTranscript]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # imported lazily, only needed here

        fetched = YouTubeTranscriptApi().fetch(video_id, languages=_PREFERRED_LANGUAGES)
        text = " ".join(
            snippet.text.strip() for snippet in fetched if getattr(snippet, "text", "").strip()
        )
        if not text.strip():
            logger.warning("fetch_transcript: video %s returned an empty transcript, skipping", video_id)
            return None
        return VideoTranscript(video_id=video_id, text=text)
    except Exception as exc:
        # Deliberately broad: covers every real failure mode the library
        # can raise (transcripts disabled, none available in our preferred
        # languages, video unavailable/private/removed, a transient block
        # from YouTube's side) with one honest "couldn't get this one"
        # outcome, the same fail-gracefully contract as fetch_page().
        logger.warning("fetch_transcript failed for video %s: %s", video_id, exc)
        return None
