"""Tests the round-by-round branching logic in debate_agent._real_debate by
monkeypatching llm_client.complete_json with canned per-provider responses —
standard test-level dependency injection (see conftest.py's module
docstring), not the product-level mock mode that was removed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.agents import debate_agent
from src.agents.monitoring_agent import MONITORING_AGENTS, run_monitoring_agent
from src.config import settings
from src.models.debate import DebateStatus
from src.services import llm_client as llm_client_module


@pytest.fixture
def two_events(stub_pipeline_calls):
    events = run_monitoring_agent(MONITORING_AGENTS[0])
    events += run_monitoring_agent(MONITORING_AGENTS[1])
    assert len(events) >= 2
    return events[:2]


def test_round1_resolves_immediately_when_no_objections(two_events, monkeypatch):
    def fake_complete_json(*, provider, model, api_key, prompt):
        assert provider == "groq"
        return {"objections": []}

    monkeypatch.setattr(llm_client_module, "complete_json", fake_complete_json)
    log = debate_agent.run_debate(two_events)
    assert log.round_count == 1
    assert {c.event_id for c in log.events} == {e.id for e in two_events}
    assert all(c.status == DebateStatus.RESOLVED for c in log.events)


def test_round2_concession_resolves_the_event(two_events, monkeypatch):
    target_id = two_events[0].id
    calls = []

    def fake_complete_json(*, provider, model, api_key, prompt):
        calls.append(provider)
        if provider == "groq":
            return {"objections": [{"event_id": target_id, "objection": "The confidence looks overstated."}]}
        assert provider != "groq"  # this is the round-2 defender call
        return {"responses": [{"event_id": target_id, "concede": True, "response": "Fair point, revising downward."}]}

    monkeypatch.setattr(llm_client_module, "complete_json", fake_complete_json)
    log = debate_agent.run_debate(two_events)
    assert log.round_count == 2
    assert calls == ["groq", settings.llm_provider]

    target = next(c for c in log.events if c.event_id == target_id)
    assert target.status == DebateStatus.RESOLVED
    assert "conceded" in target.reason.lower()
    assert len(target.positions) == 3  # original agent, Challenger, Defender

    other_id = two_events[1].id
    other = next(c for c in log.events if c.event_id == other_id)
    assert other.status == DebateStatus.RESOLVED  # never objected to in round 1


def test_round3_final_call_when_defender_holds_its_ground(two_events, monkeypatch):
    target_id = two_events[0].id
    call_sequence = []

    def fake_complete_json(*, provider, model, api_key, prompt):
        call_sequence.append(provider)
        if len(call_sequence) == 1:
            return {"objections": [{"event_id": target_id, "objection": "Source may be biased."}]}
        elif len(call_sequence) == 2:
            return {"responses": [{"event_id": target_id, "concede": False, "response": "Source is credible, standing by it."}]}
        else:
            return {"final": [{"event_id": target_id, "status": "contested", "reason": "Genuine disagreement over source credibility remains unresolved."}]}

    monkeypatch.setattr(llm_client_module, "complete_json", fake_complete_json)
    log = debate_agent.run_debate(two_events)
    assert log.round_count == 3
    assert call_sequence == ["groq", settings.llm_provider, "groq"]

    target = next(c for c in log.events if c.event_id == target_id)
    assert target.status == DebateStatus.CONTESTED
    assert "credibility" in target.reason.lower()
    assert len(target.positions) == 3


def test_missing_round3_final_call_defaults_to_uncertain_not_dropped(two_events, monkeypatch):
    target_id = two_events[0].id
    call_sequence = []

    def fake_complete_json(*, provider, model, api_key, prompt):
        call_sequence.append(provider)
        if len(call_sequence) == 1:
            return {"objections": [{"event_id": target_id, "objection": "Unclear sourcing."}]}
        elif len(call_sequence) == 2:
            return {"responses": [{"event_id": target_id, "concede": False, "response": "Sourcing is fine."}]}
        else:
            return {"final": []}  # provider returned nothing usable for this event

    monkeypatch.setattr(llm_client_module, "complete_json", fake_complete_json)
    log = debate_agent.run_debate(two_events)
    target = next(c for c in log.events if c.event_id == target_id)
    # FR-06: never silently dropped — must still appear with SOME status.
    assert target.status == DebateStatus.UNCERTAIN


def test_a_failed_real_call_propagates_honestly_not_fabricated(two_events, monkeypatch):
    """No mock fallback: if a real provider call fails partway through
    debate, that failure must reach the caller — src/orchestrator/graph.py's
    _debate_node records it as a failed step with the real error — rather
    than being papered over with a fabricated result."""

    def raising_complete_json(*, provider, model, api_key, prompt):
        raise RuntimeError("simulated provider outage")

    monkeypatch.setattr(llm_client_module, "complete_json", raising_complete_json)
    with pytest.raises(RuntimeError, match="simulated provider outage"):
        debate_agent.run_debate(two_events)
