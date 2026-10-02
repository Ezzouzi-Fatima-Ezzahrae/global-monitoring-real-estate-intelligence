import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.agents import run_debate
from src.agents.monitoring_agent import MONITORING_AGENTS, run_monitoring_agent
from src.config import settings
from src.errors import MissingConfigurationError
from src.models.debate import DebateStatus


@pytest.fixture
def some_events(stub_pipeline_calls):
    events = []
    for config in MONITORING_AGENTS[:2]:
        events.extend(run_monitoring_agent(config))
    assert len(events) >= 1
    return events


def test_no_events_returns_empty_debate_log():
    log = run_debate([])
    assert log.round_count == 0
    assert log.events == []


def test_debate_requires_llm_api_key(some_events, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(MissingConfigurationError, match="LLM_API_KEY"):
        run_debate(some_events)


def test_debate_requires_groq_api_key(some_events, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")
    with pytest.raises(MissingConfigurationError, match="GROQ_API_KEY"):
        run_debate(some_events)


def test_every_event_covered_exactly_once(some_events, stub_complete_json):
    log = run_debate(some_events)
    # FR-06 guardrail: every event that entered debate appears in exactly
    # one outcome, never silently dropped.
    debated_ids = {c.event_id for c in log.events}
    assert debated_ids == {e.id for e in some_events}
    assert len(log.events) == len(some_events)


def test_no_objections_resolves_in_round_1(some_events, stub_complete_json):
    log = run_debate(some_events)
    assert log.round_count == 1
    assert all(c.status == DebateStatus.RESOLVED for c in log.events)
    assert all(len(c.positions) >= 1 for c in log.events)


def test_debate_log_round_count_is_bounded(some_events, stub_complete_json):
    log = run_debate(some_events)
    assert 0 <= log.round_count <= 3
