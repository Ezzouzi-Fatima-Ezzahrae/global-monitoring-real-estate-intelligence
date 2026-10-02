"""Shared test fixtures.

This system has no mock/fallback mode in the product itself — see
src/errors.py's MissingConfigurationError and the module docstrings in
src/tools/web_search.py, src/tools/page_fetch.py, src/services/llm_client.py
and src/agents/debate_agent.py. What lives here is standard, test-level
dependency injection (pytest's monkeypatch): tests replace the *network-
calling* functions (web_search, fetch_page, youtube_search, fetch_transcript,
llm_client.summarize_event, llm_client.complete_json, or the httpx calls
underneath them) with deterministic fakes — the same way any test suite
avoids hitting real, paid APIs on every run. That is a property of how the
tests are written, not a code path the shipped product can fall into: the
product always calls the real thing or raises MissingConfigurationError,
never a fixture standing in for one.

Two families of fixture:
  - `fake_credentials` (autouse): gives every test a full, valid-looking set
    of API keys by default, so settings.require(...) succeeds and tests
    exercise the real code paths (with network calls stubbed) rather than
    constantly tripping the "not configured" branch. A test that wants to
    verify that branch explicitly blanks one key with monkeypatch.
  - `stub_web_search`, `stub_fetch_page`, `stub_youtube_search`,
    `stub_fetch_transcript`, `stub_summarize_event`, `stub_complete_json`,
    and the bundles `stub_pipeline_calls` / `stub_full_pipeline`: replace
    the real network calls with canned, deterministic responses. Tests that
    need specific behavior monkeypatch further within the test itself (see
    tests/test_debate_agent_real_mode_logic.py for the fullest example of
    this).
"""
from __future__ import annotations

import pytest

from src.config import settings
from src.services.llm_client import llm_client as llm_client_instance
from src.tools.page_fetch import RawPage
from src.tools.web_search import SearchResult
from src.tools.youtube_search import VideoResult
from src.tools.youtube_transcript import VideoTranscript


@pytest.fixture(autouse=True)
def fake_credentials(monkeypatch):
    """Every test gets non-empty, obviously-fake credentials by default, so
    settings.require(...) succeeds and code under test runs its real logic
    against stubbed network calls (see stub_* fixtures below) instead of
    tripping the "not configured" branch on every single test. Tests that
    specifically want to exercise MissingConfigurationError blank a key
    themselves with monkeypatch, after this fixture has run."""
    monkeypatch.setattr(settings, "llm_api_key", "test-fake-llm-key")
    monkeypatch.setattr(settings, "groq_api_key", "test-fake-groq-key")
    monkeypatch.setattr(settings, "web_search_api_key", "test-fake-search-key")
    monkeypatch.setattr(settings, "youtube_api_key", "test-fake-youtube-key")


def _canned_search_result(query: str) -> SearchResult:
    return SearchResult(
        title=f"Test article for: {query}",
        url=f"https://example.test/articles/{abs(hash(query)) % 10_000}",
        snippet="A steady, stable development with no major surprises.",
        published_date="2026-09-01",
    )


def _canned_video_result(query: str) -> VideoResult:
    return VideoResult(
        video_id=f"test{abs(hash(query)) % 10_000:04d}",
        title=f"Test video for: {query}",
        channel_title="Test Channel",
        description="A steady, stable development with no major surprises.",
        published_date="2026-09-01T12:00:00Z",
    )


@pytest.fixture
def stub_web_search(monkeypatch):
    """Patches the `web_search` name bound in src.agents.monitoring_agent
    (per `from src.tools import web_search`) so agent tests get one
    deterministic SearchResult per call instead of hitting Tavily."""

    def fake_web_search(query, source_category="global_political", max_results=5, include_domains=None, recency_days=None):
        return [_canned_search_result(query)]

    monkeypatch.setattr("src.agents.monitoring_agent.web_search", fake_web_search)
    return fake_web_search


@pytest.fixture
def stub_fetch_page(monkeypatch):
    """Patches the `fetch_page` name bound in src.agents.monitoring_agent."""

    def fake_fetch_page(url, timeout_s=None):
        return RawPage(
            url=url,
            html="<html><body><h1>Test Headline</h1><p>Steady, stable growth reported today.</p></body></html>",
        )

    monkeypatch.setattr("src.agents.monitoring_agent.fetch_page", fake_fetch_page)
    return fake_fetch_page


@pytest.fixture
def stub_youtube_search(monkeypatch):
    """Patches the `youtube_search` name bound in src.agents.monitoring_agent
    (per `from src.tools import ... youtube_search`) so the YouTube agent's
    tests get one deterministic VideoResult per call instead of hitting the
    real YouTube Data API."""

    def fake_youtube_search(query, max_results=5, recency_days=None, region_code=None):
        return [_canned_video_result(query)]

    monkeypatch.setattr("src.agents.monitoring_agent.youtube_search", fake_youtube_search)
    return fake_youtube_search


@pytest.fixture
def stub_fetch_transcript(monkeypatch):
    """Patches the `fetch_transcript` name bound in src.agents.monitoring_agent."""

    def fake_fetch_transcript(video_id):
        return VideoTranscript(video_id=video_id, text="Steady, stable growth discussed in this video today.")

    monkeypatch.setattr("src.agents.monitoring_agent.fetch_transcript", fake_fetch_transcript)
    return fake_fetch_transcript


@pytest.fixture
def stub_summarize_event(monkeypatch):
    """Patches the llm_client singleton's summarize_event directly — it's
    the same instance object every importer holds a reference to, so
    patching it here covers every caller (monitoring_agent included)."""

    def fake_summarize_event(*, agent_name, article_title, article_text, source_url):
        return {
            "summary": f"Steady, unremarkable development reported by {agent_name}.",
            "sentiment": "neutral",
            "relevance_to_real_estate": "medium",
            "confidence": 0.7,
            "agent_interpretation": "Routine update, no major shift indicated.",
        }

    monkeypatch.setattr(llm_client_instance, "summarize_event", fake_summarize_event)
    return fake_summarize_event


@pytest.fixture
def stub_complete_json(monkeypatch):
    """Patches the llm_client singleton's complete_json — used directly by
    both the debate stage (the 'defender' and 'challenger' voices) and the
    Judge stage (src/agents/judge_agent.py) — with a deterministic response
    shaped to whichever stage is calling, detected from the prompt text
    itself (Judge prompts always ask for 'sector_or_market_affected'; debate
    prompts never do). This keeps debate resolving everything in round 1 and
    gives Judge a steady, low-confidence, uncontested assessment, all without
    any real network call."""

    def fake_complete_json(*, provider, model, api_key, prompt):
        if "sector_or_market_affected" in prompt:
            return {
                "sector_or_market_affected": "prime residential demand",
                "direction": "neutral",
                "magnitude": "low",
                "confidence": 0.4,
                "time_horizon": "medium_term",
                "rationale": "The event is a steady, stable development with no major surprises, so it does not shift buyer or investor behavior on its own.",
                "recommended_action": "Monitor — no immediate action needed.",
            }
        return {"objections": []}

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)
    return fake_complete_json


@pytest.fixture
def stub_pipeline_calls(stub_web_search, stub_fetch_page, stub_youtube_search, stub_fetch_transcript, stub_summarize_event):
    """Convenience bundle: stubs the full monitoring-agent call chain for
    both source types (web_search -> fetch_page, and youtube_search ->
    fetch_transcript, either way finishing at llm_client.summarize_event)
    with deterministic, offline fakes. Most agent tests want this — in
    particular, the "every configured agent produces events" test in
    tests/test_agents.py iterates all of MONITORING_AGENTS, web and YouTube
    alike, so this bundle has to cover both retrieval pipelines."""
    return None


@pytest.fixture
def stub_full_pipeline(stub_pipeline_calls, stub_complete_json):
    """stub_pipeline_calls plus the debate stage's complete_json — for
    tests that run the whole orchestrator graph end to end."""
    return None
