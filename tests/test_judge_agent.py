import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.agents import run_judge
from src.config import settings
from src.errors import MissingConfigurationError
from src.models.debate import ContestedEvent, DebateLog, DebateStatus
from src.models.event import Event
from src.models.impact import CONTESTED_CONFIDENCE_CEILING
from src.services import knowledge_base
from src.services.llm_client import llm_client as llm_client_instance


@pytest.fixture(autouse=True)
def stub_knowledge_base_retrieve(monkeypatch):
    """Judge (Phase 5) now calls knowledge_base.retrieve() for every event
    (Phase 4 RAG, src/services/knowledge_base.py) — real, offline, lexical
    BM25 search over the actual knowledge_base/ folder on disk. These tests
    must not depend on that folder's real, evolving content (a wording
    change in a real knowledge-base markdown file should never make an
    unrelated test here start or stop matching), so every test in this file
    gets a fake that returns no matches by default. The two tests that
    specifically exercise retrieval integration monkeypatch this again
    themselves, later in the same test, which simply overrides this one."""
    monkeypatch.setattr(knowledge_base, "retrieve", lambda query, top_k=3, min_score=0.05: [])


def _event(event_id: str, headline: str = "Test headline") -> Event:
    return Event(
        id=event_id,
        agent="Test Agent",
        headline=headline,
        summary="A steady, stable development with no major surprises.",
        confidence=0.7,
        source_url=f"https://example.test/articles/{event_id}",
        retrieval_id=f"retrieval-{event_id}",
    )


def _debate_log(event_id: str, status: DebateStatus, reason: str = "") -> DebateLog:
    return DebateLog(
        round_count=1,
        events=[ContestedEvent(event_id=event_id, status=status, reason=reason)],
    )


def test_no_events_returns_empty_list():
    assert run_judge([], None) == []


def test_judge_requires_llm_api_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(MissingConfigurationError, match="LLM_API_KEY"):
        run_judge([_event("e1")], None)


def test_resolved_event_produces_uncontested_assessment(stub_complete_json):
    log = _debate_log("e1", DebateStatus.RESOLVED, reason="Consensus reached.")
    assessments = run_judge([_event("e1")], log)
    assert len(assessments) == 1
    a = assessments[0]
    assert a.event_id == "e1"
    assert a.contested is False
    assert a.supporting_evidence == ["e1"]
    assert 0.0 <= a.confidence <= 1.0
    assert a.rationale  # the Judge's plain-language "why", not just the verdict numbers


def test_contested_event_confidence_is_clamped(monkeypatch):
    """FR-08 guardrail, enforced in code (not only requested by prompt): a
    contested/uncertain event's confidence must never exceed
    CONTESTED_CONFIDENCE_CEILING, even if the model itself returned higher."""

    def fake_complete_json(*, provider, model, api_key, prompt):
        return {
            "sector_or_market_affected": "tourist-driven short-term rentals",
            "direction": "negative",
            "magnitude": "high",
            "confidence": 0.9,  # deliberately above the ceiling
            "time_horizon": "immediate",
            "recommended_action": "Watch closely.",
        }

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    log = _debate_log("e1", DebateStatus.CONTESTED, reason="Agents disagreed on severity.")
    assessments = run_judge([_event("e1")], log)
    assert len(assessments) == 1
    a = assessments[0]
    assert a.contested is True
    assert a.confidence == CONTESTED_CONFIDENCE_CEILING


def test_uncertain_event_treated_same_as_contested(monkeypatch):
    """Deliberate design choice: DebateStatus.UNCERTAIN gets the same
    confidence ceiling as CONTESTED — an event the debate stage couldn't
    confidently resolve either way deserves the same cap as one it actively
    disputed, not the benefit of the doubt."""

    def fake_complete_json(*, provider, model, api_key, prompt):
        return {
            "sector_or_market_affected": "financing and construction costs",
            "direction": "mixed",
            "magnitude": "medium",
            "confidence": 0.95,
            "time_horizon": "short_term",
            "recommended_action": "Gather more information before acting.",
        }

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    log = _debate_log("e1", DebateStatus.UNCERTAIN, reason="Insufficient evidence either way.")
    assessments = run_judge([_event("e1")], log)
    assert assessments[0].contested is True
    assert assessments[0].confidence == CONTESTED_CONFIDENCE_CEILING


def test_rationale_is_captured_from_the_model_response(monkeypatch):
    """The Judge's rationale is shown directly to Orchid Island in the
    Digest Console (it is the plain-language "why" behind the verdict, not
    just the direction/magnitude/confidence numbers) -- confirm it actually
    flows from the raw LLM response onto the ImpactAssessment verbatim."""

    def fake_complete_json(*, provider, model, api_key, prompt):
        return {
            "sector_or_market_affected": "tourist-driven short-term rentals",
            "direction": "negative",
            "magnitude": "medium",
            "confidence": 0.6,
            "time_horizon": "short_term",
            "rationale": "A new short-term rental cap directly reduces the pool of eligible units, which softens near-term yield expectations for that segment.",
            "recommended_action": "Flag for the portfolio team.",
        }

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    assessments = run_judge([_event("e1")], None)
    assert assessments[0].rationale == (
        "A new short-term rental cap directly reduces the pool of eligible units, "
        "which softens near-term yield expectations for that segment."
    )


def test_rationale_defaults_to_empty_string_when_model_omits_it(monkeypatch):
    """A model response that skips the (still fairly new) rationale field
    must not fail the whole event's assessment -- it degrades to an empty
    string, same fail-gracefully-per-field spirit as the rest of this
    module, and the GUI simply skips rendering an empty rationale."""

    def fake_complete_json(*, provider, model, api_key, prompt):
        return {
            "sector_or_market_affected": "prime residential demand",
            "direction": "positive",
            "magnitude": "low",
            "confidence": 0.3,
            "time_horizon": "medium_term",
            "recommended_action": "No action needed.",
        }

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    assessments = run_judge([_event("e1")], None)
    assert assessments[0].rationale == ""


def test_one_event_failing_does_not_blank_out_the_others(monkeypatch):
    """FR-14 fail-gracefully: one event's assessment failing (bad model
    response, transient error) must not prevent the other events' real
    assessments from coming through."""
    calls = {"n": 0}

    def flaky_complete_json(*, provider, model, api_key, prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated transient failure")
        return {
            "sector_or_market_affected": "prime residential demand",
            "direction": "positive",
            "magnitude": "low",
            "confidence": 0.5,
            "time_horizon": "medium_term",
            "recommended_action": "No action needed.",
        }

    monkeypatch.setattr(llm_client_instance, "complete_json", flaky_complete_json)

    events = [_event("e1"), _event("e2")]
    assessments = run_judge(events, None)
    assert len(assessments) == 1
    assert assessments[0].event_id == "e2"


def test_retrieved_knowledge_base_context_flows_into_prompt_and_supporting_evidence(monkeypatch):
    """Phase 4 RAG: when knowledge_base.retrieve() finds a real match for an
    event, Judge must (a) actually include that material in the prompt sent
    to the model, and (b) record it in supporting_evidence, so the report
    can show exactly which knowledge-base sections a given assessment
    leaned on -- this is the whole point of that field (see impact.py's own
    docstring: "event_ids and rag_document_ids")."""
    fake_chunk = knowledge_base.RetrievedChunk(
        source_file="market/marrakech_comparable_listings.md",
        heading="Villa (Vente) price per m2 by neighborhood, Marrakech (n >= 5)",
        text="Palmeraie villas: median price per m2 of 21,507 DH across 64 listings.",
        score=4.2,
    )
    monkeypatch.setattr(knowledge_base, "retrieve", lambda query, top_k=3, min_score=0.05: [fake_chunk])

    captured = {}

    def fake_complete_json(*, provider, model, api_key, prompt):
        captured["prompt"] = prompt
        return {
            "sector_or_market_affected": "prime residential demand",
            "direction": "positive",
            "magnitude": "medium",
            "confidence": 0.6,
            "time_horizon": "short_term",
            "rationale": "Per marrakech_comparable_listings.md, Palmeraie villa prices already command a premium.",
            "recommended_action": "Monitor Palmeraie pricing.",
        }

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    assessments = run_judge([_event("e1")], None)

    assert "marrakech_comparable_listings.md" in captured["prompt"]
    assert "Palmeraie villas: median price per m2 of 21,507 DH" in captured["prompt"]
    assert assessments[0].supporting_evidence == [
        "e1",
        "market/marrakech_comparable_listings.md#Villa (Vente) price per m2 by neighborhood, Marrakech (n >= 5)",
    ]


def test_no_knowledge_base_match_is_stated_honestly_in_the_prompt(monkeypatch):
    """When retrieval finds nothing relevant, Judge must not silently omit
    any mention of the knowledge base -- the prompt says so explicitly, so
    the model never implies company-specific grounding it doesn't actually
    have, and supporting_evidence carries only the event's own id."""
    monkeypatch.setattr(knowledge_base, "retrieve", lambda query, top_k=3, min_score=0.05: [])
    captured = {}

    def fake_complete_json(*, provider, model, api_key, prompt):
        captured["prompt"] = prompt
        return {
            "sector_or_market_affected": "prime residential demand",
            "direction": "neutral",
            "magnitude": "low",
            "confidence": 0.3,
            "time_horizon": "medium_term",
            "recommended_action": "No action needed.",
        }

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)
    assessments = run_judge([_event("e1")], None)

    assert "none of the curated knowledge base matched" in captured["prompt"]
    assert assessments[0].supporting_evidence == ["e1"]
