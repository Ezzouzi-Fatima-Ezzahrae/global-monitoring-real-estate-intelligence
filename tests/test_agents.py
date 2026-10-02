import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime

import pytest

from src.agents import MONITORING_AGENTS, MonitoringAgentConfig, run_monitoring_agent
from src.agents.monitoring_agent import _parse_published_date
from src.config import settings
from src.errors import MissingConfigurationError
from src.services.llm_client import llm_client as llm_client_instance
from src.tools.web_search import SearchResult


def test_every_configured_agent_produces_events_with_stubbed_calls(stub_pipeline_calls):
    for config in MONITORING_AGENTS:
        events = run_monitoring_agent(config)
        assert len(events) >= 1, f"{config.name} produced no events"


def test_event_is_grounded_in_a_real_retrieved_source(stub_pipeline_calls):
    config = MONITORING_AGENTS[0]
    events = run_monitoring_agent(config)
    for e in events:
        assert str(e.source_url).startswith("http")
        assert e.retrieval_id  # every event traces back to a retrieval


def test_agent_skips_one_bad_article_without_crashing(stub_web_search, stub_fetch_page, monkeypatch):
    """One bad article must not kill the whole agent run (FR-14): here the
    LLM summarization step genuinely fails for every article, so the agent
    should come back with zero events rather than raising."""

    def raising_summarize(*, agent_name, article_title, article_text, source_url):
        raise ValueError("simulated summarization failure")

    monkeypatch.setattr(llm_client_instance, "summarize_event", raising_summarize)
    events = run_monitoring_agent(MONITORING_AGENTS[0])
    assert events == []


def test_agent_propagates_missing_configuration_loudly(monkeypatch):
    """A missing credential is not a per-source outage — it must not be
    swallowed into a silent empty result. web_search() raises
    MissingConfigurationError before any network call is attempted, and
    run_monitoring_agent must let it propagate rather than catching it like
    an ordinary search failure."""
    monkeypatch.setattr(settings, "web_search_api_key", "")
    with pytest.raises(MissingConfigurationError, match="WEB_SEARCH_API_KEY"):
        run_monitoring_agent(MONITORING_AGENTS[0])


def test_agent_propagates_missing_llm_key_rather_than_skipping_every_article(
    stub_web_search, stub_fetch_page, monkeypatch
):
    """Same principle, at the per-article summarization call: a missing
    LLM_API_KEY would otherwise look identical to 'every single article
    individually failed to summarize', which hides the real cause."""
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(MissingConfigurationError, match="LLM_API_KEY"):
        run_monitoring_agent(MONITORING_AGENTS[0])


def test_agent_with_unresolvable_page_fetch_fails_gracefully(stub_web_search, monkeypatch):
    """fetch_page returning None (a genuine, honest per-URL failure) must
    not crash the agent run or fabricate an event for that URL."""
    monkeypatch.setattr("src.agents.monitoring_agent.fetch_page", lambda url, timeout_s=None: None)
    events = run_monitoring_agent(MONITORING_AGENTS[0])
    assert events == []


def test_parse_published_date_handles_iso_and_rfc2822():
    assert _parse_published_date("2026-09-04") == datetime.date(2026, 9, 4)
    # Real format returned by Tavily in news mode — found via a real run:
    # this used to raise inside Event's pydantic validation and silently
    # drop the event (see run_monitoring_agent's per-article except).
    assert _parse_published_date("Fri, 04 Sep 2026 20:34:06 GMT") == datetime.date(2026, 9, 4)
    assert _parse_published_date(None) is None
    assert _parse_published_date("not a date") is None


def test_agent_skips_articles_judged_low_relevance(stub_web_search, stub_fetch_page, monkeypatch):
    """2026-09-17, at Orchid Island's request: an item whose real content
    the AI judges "low" relevance to real estate must not appear in the
    report at all -- previously "low" only changed a display pill, so
    off-topic matches (e.g. a page that only mentions the query terms in
    passing) still made it into the digest. One real article -> a
    genuinely low-relevance summary -> zero events."""

    def low_relevance_summarize(*, agent_name, article_title, article_text, source_url):
        return {
            "summary": "Only tangentially mentions the topic.",
            "sentiment": "neutral",
            "relevance_to_real_estate": "low",
            "confidence": 0.6,
            "agent_interpretation": "Not actually useful for real-estate monitoring.",
        }

    monkeypatch.setattr(llm_client_instance, "summarize_event", low_relevance_summarize)
    events = run_monitoring_agent(MONITORING_AGENTS[0])
    assert events == []


def test_agent_keeps_articles_judged_medium_or_high_relevance(stub_web_search, stub_fetch_page, monkeypatch):
    """Companion to the low-relevance skip above: the gate must only
    exclude "low" -- "medium" and "high" are real, useful signal and must
    still produce events, so this isn't accidentally an allow-list of one
    value or a filter that drops everything."""

    def make_summarize(relevance):
        def fake_summarize(*, agent_name, article_title, article_text, source_url):
            return {
                "summary": "Relevant development.",
                "sentiment": "neutral",
                "relevance_to_real_estate": relevance,
                "confidence": 0.6,
                "agent_interpretation": "Worth tracking.",
            }

        return fake_summarize

    for relevance in ("medium", "high"):
        monkeypatch.setattr(llm_client_instance, "summarize_event", make_summarize(relevance))
        events = run_monitoring_agent(MONITORING_AGENTS[0])
        assert len(events) == 1, f"expected an event for relevance={relevance!r}"


def test_agent_does_not_drop_event_on_rfc2822_published_date(stub_fetch_page, stub_summarize_event, monkeypatch):
    """Regression test for a real bug: Tavily's news-mode results (used by
    the political/economic/expert-commentary agents' recency_days=7) return
    published_date as an RFC 2822 string, which Event's date field can't
    parse directly. Before the _parse_published_date fix, this silently
    turned every real event from those agents into a caught, logged, and
    discarded per-article failure — a real event was there and got dropped,
    not fabricated, but still a bug worth locking in."""

    def fake_web_search(query, source_category="global_political", max_results=5, include_domains=None, recency_days=None):
        return [
            SearchResult(
                title="Real headline",
                url="https://example.test/real-article",
                snippet="snippet",
                published_date="Fri, 04 Sep 2026 20:34:06 GMT",
            )
        ]

    monkeypatch.setattr("src.agents.monitoring_agent.web_search", fake_web_search)
    events = run_monitoring_agent(MONITORING_AGENTS[0])
    assert len(events) == 1
    assert events[0].published_at == datetime.date(2026, 9, 4)
