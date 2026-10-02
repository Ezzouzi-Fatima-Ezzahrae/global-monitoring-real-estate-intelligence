"""Tests for src/tools/youtube_search.py and src/tools/youtube_transcript.py.

Same technique as tests/test_tools.py: stub the HTTP transport (httpx) or
the youtube_transcript_api library underneath the real code, rather than
hitting a real, quota-limited API on every test run. The parsing, error
handling, and MissingConfigurationError logic being exercised is the actual
production code path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

from src.config import settings
from src.errors import MissingConfigurationError
from src.tools import fetch_transcript, youtube_search


def test_youtube_search_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "youtube_api_key", "")
    with pytest.raises(MissingConfigurationError, match="YOUTUBE_API_KEY"):
        youtube_search("anything")


def test_youtube_search_builds_request_and_parses_a_real_response_shape(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": {"videoId": "abc123"},
                        "snippet": {
                            "title": "Real video title",
                            "channelTitle": "Real Channel",
                            "description": "A description",
                            "publishedAt": "2026-09-01T10:00:00Z",
                        },
                    }
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    results = youtube_search("marrakech real estate", max_results=3)

    assert captured["url"] == "https://www.googleapis.com/youtube/v3/search"
    assert captured["params"]["key"] == "test-fake-youtube-key"
    assert captured["params"]["q"] == "marrakech real estate"
    assert captured["params"]["type"] == "video"
    assert "publishedAfter" not in captured["params"]  # recency_days not passed -> not sent
    assert len(results) == 1
    assert results[0].video_id == "abc123"
    assert results[0].title == "Real video title"
    assert results[0].url == "https://www.youtube.com/watch?v=abc123"


def test_youtube_search_unescapes_html_entities_in_title(monkeypatch):
    """2026-09-21 regression: a real live run returned a real video title as
    "...il n&#39;y a aucun avenir !" -- the YouTube Data API sends
    title/channelTitle/description HTML-escaped, and nothing downstream
    (report, web console, PDF export) undoes that, so it would show up
    broken everywhere this text is displayed. Confirms it's decoded once,
    at the source."""

    def fake_get(url, params=None, timeout=None):
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": {"videoId": "abc123"},
                        "snippet": {
                            "title": "il n&#39;y a aucun avenir &amp; c&#39;est &quot;grave&quot;",
                            "channelTitle": "Vivre &amp; Investir",
                            "description": "Tom &amp; Jerry talk real estate",
                            "publishedAt": "2026-09-01T10:00:00Z",
                        },
                    }
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    results = youtube_search("x")

    assert results[0].title == 'il n\'y a aucun avenir & c\'est "grave"'
    assert results[0].channel_title == "Vivre & Investir"
    assert results[0].description == "Tom & Jerry talk real estate"


def test_youtube_search_passes_recency_days_as_published_after(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return httpx.Response(200, json={"items": []}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    youtube_search("morocco tourism", recency_days=14)

    assert "publishedAfter" in captured["params"]
    assert captured["params"]["publishedAfter"].endswith("Z")


def test_youtube_search_skips_items_with_no_video_id(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return httpx.Response(
            200,
            json={"items": [{"id": {}, "snippet": {"title": "No id here"}}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    assert youtube_search("x") == []


def test_youtube_search_transient_failure_returns_empty_not_raise(monkeypatch):
    def raising_get(*args, **kwargs):
        raise httpx.ConnectError("simulated network blip")

    monkeypatch.setattr(httpx, "get", raising_get)
    # An honest empty result on a genuine transient failure (FR-14) — not a
    # fixture standing in for real data.
    assert youtube_search("x") == []


def test_fetch_transcript_joins_snippet_text(monkeypatch):
    class FakeSnippet:
        def __init__(self, text):
            self.text = text

    class FakeApi:
        def fetch(self, video_id, languages=None):
            assert video_id == "abc123"
            assert languages == ["ar", "fr", "en"]
            return [FakeSnippet("Hello"), FakeSnippet("world.")]

    import youtube_transcript_api

    monkeypatch.setattr(youtube_transcript_api, "YouTubeTranscriptApi", FakeApi)
    result = fetch_transcript("abc123")
    assert result is not None
    assert result.video_id == "abc123"
    assert "Hello" in result.text and "world." in result.text


def test_fetch_transcript_returns_none_on_genuine_failure(monkeypatch):
    class FakeApi:
        def fetch(self, video_id, languages=None):
            raise RuntimeError("simulated: transcripts disabled for this video")

    import youtube_transcript_api

    monkeypatch.setattr(youtube_transcript_api, "YouTubeTranscriptApi", FakeApi)
    # An honest None on a genuine per-video failure — not a fabricated transcript.
    assert fetch_transcript("no-captions-video") is None


def test_fetch_transcript_returns_none_on_empty_transcript(monkeypatch):
    class FakeApi:
        def fetch(self, video_id, languages=None):
            return []

    import youtube_transcript_api

    monkeypatch.setattr(youtube_transcript_api, "YouTubeTranscriptApi", FakeApi)
    assert fetch_transcript("empty-video") is None
