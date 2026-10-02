"""Tests for src/services/chat_assistant.py -- the real-report Q&A chat
assistant behind POST /chat (2026-09-16 addition, replacing the earlier
per-event notes boxes). Same offline-by-stubbing convention as the rest of
the suite (see conftest.py's module docstring): llm_client.complete_json
and knowledge_base.retrieve are replaced with deterministic fakes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

from src.config import settings
from src.errors import MissingConfigurationError
from src.services import chat_assistant, knowledge_base
from src.services.llm_client import llm_client as llm_client_instance


def _rate_limited_error():
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/fake")
    response = httpx.Response(429, request=request, text="rate limited")
    return httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)


@pytest.fixture(autouse=True)
def stub_knowledge_base_retrieve(monkeypatch):
    """Every test here gets no KB matches by default (this suite must not
    depend on the real, evolving knowledge_base/ folder on disk) -- the one
    test that exercises retrieval integration overrides this itself."""
    monkeypatch.setattr(knowledge_base, "retrieve", lambda query, top_k=4, min_score=0.05: [])


def _run(events=None, impact_analysis=None):
    return {
        "run_date": "2026-09-16",
        "events": events or [],
        "report": {
            "headline": "A quiet day for Marrakech real estate.",
            "impact_analysis": impact_analysis or [],
        },
    }


def test_requires_llm_api_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(MissingConfigurationError, match="LLM_API_KEY"):
        chat_assistant.answer_question(run=None, question="What happened today?")


def test_answers_using_stubbed_llm_and_no_run_loaded(monkeypatch):
    captured = {}

    def fake_complete_json(*, provider, model, api_key, prompt):
        captured["prompt"] = prompt
        return {"answer": "No report is loaded right now, so I can't answer that from today's events."}

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    result = chat_assistant.answer_question(run=None, question="What's the biggest risk today?")

    assert result["answer"] == "No report is loaded right now, so I can't answer that from today's events."
    assert result["sources"] == []
    assert "No daily report is currently loaded" in captured["prompt"]
    assert "What's the biggest risk today?" in captured["prompt"]


def test_report_events_and_impact_flow_into_the_prompt(monkeypatch):
    captured = {}

    def fake_complete_json(*, provider, model, api_key, prompt):
        captured["prompt"] = prompt
        return {"answer": "Rates hint at a slower quarter for villa sales."}

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    run = _run(
        events=[
            {
                "id": "e1",
                "agent": "Global Economic & Markets Agent",
                "headline": "Bank Al-Maghrib holds rates steady",
                "summary": "The central bank kept its policy rate unchanged this quarter.",
                "sentiment": "neutral",
                "relevance_to_real_estate": "medium",
                "source_name": "Reuters",
            }
        ],
        impact_analysis=[
            {
                "event_id": "e1",
                "sector_or_market_affected": "Residential financing",
                "direction": "neutral",
                "magnitude": "low",
                "rationale": "Stable rates keep mortgage costs predictable for buyers.",
                "recommended_action": "No action needed this week.",
            }
        ],
    )

    result = chat_assistant.answer_question(run=run, question="What did the economic agent find?")

    assert result["answer"] == "Rates hint at a slower quarter for villa sales."
    assert "Bank Al-Maghrib holds rates steady" in captured["prompt"]
    assert "Stable rates keep mortgage costs predictable for buyers." in captured["prompt"]
    assert "What did the economic agent find?" in captured["prompt"]


def test_knowledge_base_matches_flow_into_prompt_and_sources(monkeypatch):
    class FakeChunk:
        def __init__(self, source_file, heading, text, score):
            self.source_file = source_file
            self.heading = heading
            self.text = text
            self.score = score

        @property
        def citation(self):
            return f"{self.source_file}#{self.heading}"

    fake_chunk = FakeChunk("company/orchid_island_listing_sidi_ghanem.md", "What the property is", "A building in the Sidi Ghanem industrial zone.", 12.0)
    monkeypatch.setattr(knowledge_base, "retrieve", lambda query, top_k=4, min_score=0.05: [fake_chunk])

    captured = {}

    def fake_complete_json(*, provider, model, api_key, prompt):
        captured["prompt"] = prompt
        return {"answer": "Sidi Ghanem has two shops and offices across two floors."}

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    result = chat_assistant.answer_question(run=None, question="What do we own in Sidi Ghanem?")

    assert result["sources"] == ["company/orchid_island_listing_sidi_ghanem.md#What the property is"]
    assert "A building in the Sidi Ghanem industrial zone." in captured["prompt"]


def test_conversation_history_flows_into_prompt(monkeypatch):
    captured = {}

    def fake_complete_json(*, provider, model, api_key, prompt):
        captured["prompt"] = prompt
        return {"answer": "Yes, that's the same event I mentioned."}

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    history = [
        {"role": "user", "text": "Anything about interest rates today?"},
        {"role": "assistant", "text": "Bank Al-Maghrib held rates steady this quarter."},
    ]
    chat_assistant.answer_question(run=None, question="Is that the one affecting mortgages?", history=history)

    assert "Anything about interest rates today?" in captured["prompt"]
    assert "Bank Al-Maghrib held rates steady this quarter." in captured["prompt"]


def test_raises_when_model_response_has_no_answer_field(monkeypatch):
    monkeypatch.setattr(llm_client_instance, "complete_json", lambda **kwargs: {"unexpected": "shape"})
    with pytest.raises(ValueError, match="no 'answer' field"):
        chat_assistant.answer_question(run=None, question="Anything interesting?")


def test_falls_back_to_groq_when_primary_provider_is_rate_limited(monkeypatch):
    """2026-09-16: a live test against the real API showed Gemini's own
    429 outlasting llm_client's internal retries, which made the chat
    panel simply fail instead of answering. Confirms the fallback actually
    fires and that it's Groq (not Gemini again) that answers."""
    monkeypatch.setattr(settings, "groq_api_key", "test-fake-groq-key")
    monkeypatch.setattr(settings, "groq_model", "test-groq-model")
    calls = []

    def fake_complete_json(*, provider, model, api_key, prompt):
        calls.append(provider)
        if provider == settings.llm_provider:
            raise _rate_limited_error()
        assert provider == "groq"
        assert model == "test-groq-model"
        return {"answer": "Groq answered since Gemini was rate-limited."}

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    result = chat_assistant.answer_question(run=None, question="What happened today?")

    assert result["answer"] == "Groq answered since Gemini was rate-limited."
    assert calls == [settings.llm_provider, "groq"]


def test_does_not_fall_back_to_groq_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")

    def fake_complete_json(*, provider, model, api_key, prompt):
        raise _rate_limited_error()

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    with pytest.raises(httpx.HTTPStatusError):
        chat_assistant.answer_question(run=None, question="What happened today?")


def test_does_not_fall_back_on_a_non_rate_limit_error(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "test-fake-groq-key")
    calls = []

    def fake_complete_json(*, provider, model, api_key, prompt):
        calls.append(provider)
        request = httpx.Request("POST", "https://generativelanguage.googleapis.com/fake")
        response = httpx.Response(400, request=request, text="bad request")
        raise httpx.HTTPStatusError("400 Bad Request", request=request, response=response)

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    with pytest.raises(httpx.HTTPStatusError):
        chat_assistant.answer_question(run=None, question="What happened today?")
    assert calls == [settings.llm_provider]  # never tried Groq for a non-429 failure
