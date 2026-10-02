"""Tests for the YouTube path of src/agents/monitoring_agent.py
(_run_youtube_agent, dispatched via run_monitoring_agent when
config.source_type == "youtube"). Mirrors the web-agent tests in
tests/test_agents.py: same error-handling contract, different retrieval
pipeline (youtube_search -> fetch_transcript instead of
web_search -> fetch_page -> extract_content).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.agents import MONITORING_AGENTS, run_monitoring_agent
from src.config import settings
from src.errors import MissingConfigurationError

YOUTUBE_AGENT = next(c for c in MONITORING_AGENTS if c.source_type == "youtube")


def test_youtube_agent_is_configured():
    """Locks in that the 6th agent (2026-09-16 addition) is actually wired
    into MONITORING_AGENTS -- if this ever stops finding one, the graph
    silently stops running YouTube monitoring at all (build_graph() just
    iterates MONITORING_AGENTS, so a missing entry is a silent no-op, not
    an error)."""
    assert YOUTUBE_AGENT.name == "YouTube Video Monitoring Agent"
    assert YOUTUBE_AGENT.source_category == "youtube_video"


def test_youtube_agent_produces_events_with_stubbed_calls(stub_youtube_search, stub_fetch_transcript, stub_summarize_event):
    events = run_monitoring_agent(YOUTUBE_AGENT)
    assert len(events) == 1
    event = events[0]
    assert str(event.source_url).startswith("https://www.youtube.com/watch?v=")
    assert event.retrieval_id  # every event traces back to a retrieval
    assert "Test Channel" in event.source_name  # real channel name carried through, not dropped


def test_youtube_agent_skips_video_with_no_usable_transcript(stub_youtube_search, monkeypatch):
    """A video with captions disabled (fetch_transcript returns None, an
    honest per-video failure) must not crash the agent run or fabricate an
    event for that video -- same principle as the web agent's
    unresolvable-page-fetch test."""
    monkeypatch.setattr("src.agents.monitoring_agent.fetch_transcript", lambda video_id: None)
    events = run_monitoring_agent(YOUTUBE_AGENT)
    assert events == []


def test_youtube_agent_propagates_missing_youtube_api_key(monkeypatch):
    """A missing YOUTUBE_API_KEY is not a per-video outage -- it must not be
    swallowed into a silent empty result, the same principle already
    enforced for WEB_SEARCH_API_KEY and LLM_API_KEY."""
    monkeypatch.setattr(settings, "youtube_api_key", "")
    with pytest.raises(MissingConfigurationError, match="YOUTUBE_API_KEY"):
        run_monitoring_agent(YOUTUBE_AGENT)


def test_youtube_agent_propagates_missing_llm_key_rather_than_skipping_every_video(
    stub_youtube_search, stub_fetch_transcript, monkeypatch
):
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(MissingConfigurationError, match="LLM_API_KEY"):
        run_monitoring_agent(YOUTUBE_AGENT)


def test_youtube_agent_skips_one_bad_video_without_crashing(stub_youtube_search, stub_fetch_transcript, monkeypatch):
    """One bad video must not kill the whole agent run (FR-14): here the
    LLM summarization step genuinely fails for every video, so the agent
    should come back with zero events rather than raising."""
    from src.services.llm_client import llm_client as llm_client_instance

    def raising_summarize(*, agent_name, article_title, article_text, source_url):
        raise ValueError("simulated summarization failure")

    monkeypatch.setattr(llm_client_instance, "summarize_event", raising_summarize)
    events = run_monitoring_agent(YOUTUBE_AGENT)
    assert events == []


def test_youtube_agent_skips_videos_judged_low_relevance(stub_youtube_search, stub_fetch_transcript, monkeypatch):
    """2026-09-17, at Orchid Island's request: a video whose real transcript
    the AI judges "low" relevance (e.g. it only mentions Marrakech/real
    estate in passing) must not appear in the report -- mirrors the same
    fix and test in tests/test_agents.py for the web agents."""
    from src.services.llm_client import llm_client as llm_client_instance

    def low_relevance_summarize(*, agent_name, article_title, article_text, source_url):
        return {
            "summary": "Only tangentially related.",
            "sentiment": "neutral",
            "relevance_to_real_estate": "low",
            "confidence": 0.6,
            "agent_interpretation": "Not actually useful for real-estate monitoring.",
        }

    monkeypatch.setattr(llm_client_instance, "summarize_event", low_relevance_summarize)
    events = run_monitoring_agent(YOUTUBE_AGENT)
    assert events == []


def test_youtube_agent_uses_real_video_published_date(stub_fetch_transcript, stub_summarize_event, monkeypatch):
    """Regression-style test for the same date-parsing path the web agents
    rely on (_parse_published_date): the YouTube Data API's publishedAt is
    RFC 3339 ("2026-09-04T12:00:00Z"), which the ISO-prefix branch already
    handles -- this locks in that the YouTube agent actually reaches that
    date rather than leaving published_at unset."""
    import datetime

    from src.tools.youtube_search import VideoResult

    def fake_youtube_search(query, max_results=5, recency_days=None, region_code=None):
        return [
            VideoResult(
                video_id="realdate1",
                title="Real video",
                channel_title="Real Channel",
                description="desc",
                published_date="2026-09-04T20:34:06Z",
            )
        ]

    monkeypatch.setattr("src.agents.monitoring_agent.youtube_search", fake_youtube_search)
    events = run_monitoring_agent(YOUTUBE_AGENT)
    assert len(events) == 1
    assert events[0].published_at == datetime.date(2026, 9, 4)
