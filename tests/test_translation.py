"""Tests for the 2026-09-22 on-demand translation feature: src/services/
translation.py (the real LLM call + guardrails), src/services/
run_persistence.py's and src/services/document_store.py's
get_or_create_translation (the translate-once-and-cache layer), and the
two new GET .../translation/{lang} routes plus /chat's new `lang` field in
src/api/main.py.

Same testing approach as tests/test_run_persistence.py and
tests/test_notifications_api.py: llm_client.complete_json is mocked (never
a real network call in this suite), but everything around it -- the
prompt building, the guardrail validation, the read-modify-write caching,
the route wiring -- is exercised for real.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.errors import MissingConfigurationError
from src.services import document_store, run_persistence, translation


# ---------------------------------------------------------------------
# translation.py -- guardrails
# ---------------------------------------------------------------------

def _sample_run():
    return {
        "report": {
            "headline": "Strong tourism signals",
            "recommended_actions": ["Do X", "Do Y"],
            "debate_highlights": ["One contested event"],
            "impact_analysis": [
                {
                    "event_id": "evt-1",
                    "sector_or_market_affected": "Hospitality",
                    "rationale": "because arrivals rose",
                    "recommended_action": "Act now",
                },
            ],
        },
        "events": [
            {"id": "evt-1", "headline": "Tourist arrivals up", "summary": "Arrivals rose 12%."},
        ],
    }


def test_translate_run_unsupported_language_raises():
    with pytest.raises(ValueError, match="Unsupported translation language"):
        translation.translate_run(_sample_run(), "es")


def test_translate_run_happy_path_returns_validated_translation():
    fake_response = {
        "report_headline": "Signaux touristiques forts",
        "recommended_actions": ["Faire X", "Faire Y"],
        "debate_highlights": ["Un evenement conteste"],
        "events": [{"id": "evt-1", "headline": "Hausse des arrivees", "summary": "Les arrivees ont augmente de 12%."}],
        "impact_assessments": [
            {"event_id": "evt-1", "sector_or_market_affected": "Hotellerie", "rationale": "car X", "recommended_action": "Agir"}
        ],
    }
    with patch.object(translation, "_call_llm", return_value=fake_response) as mock_call:
        result = translation.translate_run(_sample_run(), "fr")
    assert result["report_headline"] == "Signaux touristiques forts"
    assert mock_call.call_count == 1
    # the real content was actually placed in the prompt sent to the model
    prompt = mock_call.call_args[0][0]
    assert "Tourist arrivals up" in prompt
    assert "French" in prompt


def test_translate_run_rejects_mismatched_event_ids():
    fake_response = {
        "report_headline": "x", "recommended_actions": ["a", "b"], "debate_highlights": ["c"],
        "events": [{"id": "evt-WRONG", "headline": "h", "summary": "s"}],
        "impact_assessments": [{"event_id": "evt-1", "sector_or_market_affected": "x", "rationale": "y", "recommended_action": "z"}],
    }
    with patch.object(translation, "_call_llm", return_value=fake_response):
        with pytest.raises(ValueError, match="do not match source event ids"):
            translation.translate_run(_sample_run(), "fr")


def test_translate_run_rejects_dropped_recommended_action():
    fake_response = {
        "report_headline": "x", "recommended_actions": ["only one"], "debate_highlights": ["c"],
        "events": [{"id": "evt-1", "headline": "h", "summary": "s"}],
        "impact_assessments": [{"event_id": "evt-1", "sector_or_market_affected": "x", "rationale": "y", "recommended_action": "z"}],
    }
    with patch.object(translation, "_call_llm", return_value=fake_response):
        with pytest.raises(ValueError, match="recommended_actions count"):
            translation.translate_run(_sample_run(), "fr")


def test_translate_run_rejects_dropped_impact_assessment():
    fake_response = {
        "report_headline": "x", "recommended_actions": ["a", "b"], "debate_highlights": ["c"],
        "events": [{"id": "evt-1", "headline": "h", "summary": "s"}],
        "impact_assessments": [],  # dropped the one real impact assessment
    }
    with patch.object(translation, "_call_llm", return_value=fake_response):
        with pytest.raises(ValueError, match="impact assessments do not match"):
            translation.translate_run(_sample_run(), "fr")


def _sample_run_with_hook():
    run = _sample_run()
    run["events"][0]["hook"] = {
        "headline": "\U0001F6A8 HOTEL GROUP MAY BE EXPLORING MARRAKECH",
        "why_it_matters": "because arrivals rose",
        "potential_requirements": ["hotel_resort_property"],
        "stage": "early_signal",
        "confidence_label": "medium",
        "evidence": "Arrivals rose 12%.",
        "suggested_action": "Act now",
    }
    return run


def test_translate_run_happy_path_includes_hook_in_prompt_and_payload():
    fake_response = {
        "report_headline": "Signaux touristiques forts",
        "recommended_actions": ["Faire X", "Faire Y"],
        "debate_highlights": ["Un evenement conteste"],
        "events": [{"id": "evt-1", "headline": "Hausse des arrivees", "summary": "Les arrivees ont augmente de 12%."}],
        "impact_assessments": [
            {"event_id": "evt-1", "sector_or_market_affected": "Hotellerie", "rationale": "car X", "recommended_action": "Agir"}
        ],
        "hooks": [
            {
                "event_id": "evt-1",
                "headline": "\U0001F6A8 GROUPE HOTELIER PEUT EXPLORER MARRAKECH",
                "why_it_matters": "car les arrivees ont augmente",
                "evidence": "Les arrivees ont augmente de 12%.",
                "suggested_action": "Agir maintenant",
            }
        ],
    }
    with patch.object(translation, "_call_llm", return_value=fake_response) as mock_call:
        result = translation.translate_run(_sample_run_with_hook(), "fr")
    assert result["hooks"][0]["headline"] == "\U0001F6A8 GROUPE HOTELIER PEUT EXPLORER MARRAKECH"
    # the real hook content (not potential_requirements -- that's static i18n, see
    # translation.py's docstring) was actually placed in the prompt sent to the model
    prompt = mock_call.call_args[0][0]
    assert "HOTEL GROUP MAY BE EXPLORING MARRAKECH" in prompt
    assert "hotel_resort_property" not in prompt


def test_translate_run_without_any_hook_events_sends_empty_hooks_list():
    fake_response = {
        "report_headline": "x", "recommended_actions": ["a", "b"], "debate_highlights": ["c"],
        "events": [{"id": "evt-1", "headline": "h", "summary": "s"}],
        "impact_assessments": [{"event_id": "evt-1", "sector_or_market_affected": "x", "rationale": "y", "recommended_action": "z"}],
        "hooks": [],
    }
    with patch.object(translation, "_call_llm", return_value=fake_response) as mock_call:
        translation.translate_run(_sample_run(), "fr")
    payload = json.loads(mock_call.call_args[0][0].split("=== CONTENT TO TRANSLATE ===\n")[1].split("\n\nRespond")[0])
    assert payload["hooks"] == []


def test_translate_run_rejects_dropped_hook():
    fake_response = {
        "report_headline": "x", "recommended_actions": ["a", "b"], "debate_highlights": ["c"],
        "events": [{"id": "evt-1", "headline": "h", "summary": "s"}],
        "impact_assessments": [{"event_id": "evt-1", "sector_or_market_affected": "x", "rationale": "y", "recommended_action": "z"}],
        "hooks": [],  # dropped the one real hook
    }
    with patch.object(translation, "_call_llm", return_value=fake_response):
        with pytest.raises(ValueError, match="hooks do not match"):
            translation.translate_run(_sample_run_with_hook(), "fr")


def test_translate_run_rejects_invented_hook_for_an_event_that_has_none():
    fake_response = {
        "report_headline": "x", "recommended_actions": ["a", "b"], "debate_highlights": ["c"],
        "events": [{"id": "evt-1", "headline": "h", "summary": "s"}],
        "impact_assessments": [{"event_id": "evt-1", "sector_or_market_affected": "x", "rationale": "y", "recommended_action": "z"}],
        "hooks": [{"event_id": "evt-1", "headline": "invented", "why_it_matters": "x", "evidence": "y", "suggested_action": "z"}],
    }
    with patch.object(translation, "_call_llm", return_value=fake_response):
        with pytest.raises(ValueError, match="hooks do not match"):
            translation.translate_run(_sample_run(), "fr")  # _sample_run's event has no hook


def test_translate_run_requires_llm_key(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(MissingConfigurationError):
        translation.translate_run(_sample_run(), "fr")


def test_translate_document_events_happy_path_and_guardrail():
    events = [{"id": "doc-evt-1", "headline": "H", "summary": "S"}]
    fake_ok = {"events": [{"id": "doc-evt-1", "headline": "H-ar", "summary": "S-ar"}]}
    with patch.object(translation, "_call_llm", return_value=fake_ok):
        result = translation.translate_document_events(events, "ar")
    assert result["events"][0]["headline"] == "H-ar"

    fake_bad = {"events": []}
    with patch.object(translation, "_call_llm", return_value=fake_bad):
        with pytest.raises(ValueError, match="do not match source event ids"):
            translation.translate_document_events(events, "ar")


# ---------------------------------------------------------------------
# run_persistence.get_or_create_translation -- translate once, cache after
# ---------------------------------------------------------------------

def test_run_translation_is_cached_after_first_call(tmp_path):
    run_id = "20260101T000000Z-abcdef"
    run = _sample_run()
    run["run_id"] = run_id
    (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")

    fake_translation = {
        "report_headline": "FR headline", "recommended_actions": ["a", "b"], "debate_highlights": ["c"],
        "events": [{"id": "evt-1", "headline": "h", "summary": "s"}],
        "impact_assessments": [{"event_id": "evt-1", "sector_or_market_affected": "x", "rationale": "y", "recommended_action": "z"}],
    }
    mock_translate = MagicMock(return_value=fake_translation)
    with patch.object(translation, "translate_run", mock_translate):
        first = run_persistence.get_or_create_translation(run_id, "fr", runs_dir=tmp_path)
        second = run_persistence.get_or_create_translation(run_id, "fr", runs_dir=tmp_path)

    assert mock_translate.call_count == 1  # second call was a pure cache read
    assert first == second == fake_translation

    persisted = json.loads((tmp_path / f"{run_id}.json").read_text(encoding="utf-8"))
    assert persisted["translations"]["fr"]["report_headline"] == "FR headline"


def test_run_translation_unknown_run_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_persistence.get_or_create_translation("does-not-exist", "fr", runs_dir=tmp_path)


def test_run_translation_failure_is_not_cached(tmp_path):
    run_id = "20260101T000000Z-abcdef"
    run = _sample_run()
    run["run_id"] = run_id
    (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")

    with patch.object(translation, "translate_run", side_effect=ValueError("bad model output")):
        with pytest.raises(ValueError):
            run_persistence.get_or_create_translation(run_id, "fr", runs_dir=tmp_path)

    persisted = json.loads((tmp_path / f"{run_id}.json").read_text(encoding="utf-8"))
    assert "translations" not in persisted or "fr" not in persisted.get("translations", {})


# ---------------------------------------------------------------------
# document_store.get_or_create_translation
# ---------------------------------------------------------------------

def test_document_translation_is_cached_after_first_call(tmp_path):
    doc_id = "20260101T000000Z-abcdef"
    record = {"document_id": doc_id, "events": [{"id": "doc-evt-1", "headline": "H", "summary": "S"}]}
    (tmp_path / f"{doc_id}.json").write_text(json.dumps(record), encoding="utf-8")

    fake = {"events": [{"id": "doc-evt-1", "headline": "H-ar", "summary": "S-ar"}]}
    mock_translate = MagicMock(return_value=fake)
    with patch.object(translation, "translate_document_events", mock_translate):
        first = document_store.get_or_create_translation(doc_id, "ar", documents_dir=tmp_path)
        second = document_store.get_or_create_translation(doc_id, "ar", documents_dir=tmp_path)

    assert mock_translate.call_count == 1
    assert first == second == fake


def test_document_translation_unknown_document_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        document_store.get_or_create_translation("does-not-exist", "ar", documents_dir=tmp_path)


# ---------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------

def test_get_run_translation_route_rejects_unsupported_language(tmp_path, monkeypatch):
    import src.api.main as api_main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)
    client = TestClient(api_main.app)
    resp = client.get("/runs/some-run/translation/es")
    assert resp.status_code == 400


def test_get_run_translation_route_404s_on_unknown_run(tmp_path, monkeypatch):
    import src.api.main as api_main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)
    client = TestClient(api_main.app)
    resp = client.get("/runs/does-not-exist/translation/fr")
    assert resp.status_code == 404


def test_get_run_translation_route_503s_on_missing_llm_key(tmp_path, monkeypatch):
    import src.api.main as api_main
    from fastapi.testclient import TestClient
    from src.config import settings

    run_id = "20260101T000000Z-abcdef"
    (tmp_path / f"{run_id}.json").write_text(json.dumps(_sample_run()), encoding="utf-8")
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(settings, "llm_api_key", "")

    client = TestClient(api_main.app)
    resp = client.get(f"/runs/{run_id}/translation/fr")
    assert resp.status_code == 503


def test_get_run_translation_route_returns_translation_and_caches(tmp_path, monkeypatch):
    import src.api.main as api_main
    from fastapi.testclient import TestClient

    run_id = "20260101T000000Z-abcdef"
    (tmp_path / f"{run_id}.json").write_text(json.dumps(_sample_run()), encoding="utf-8")
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)

    fake_translation = {
        "report_headline": "FR headline", "recommended_actions": ["a", "b"], "debate_highlights": ["c"],
        "events": [{"id": "evt-1", "headline": "h", "summary": "s"}],
        "impact_assessments": [{"event_id": "evt-1", "sector_or_market_affected": "x", "rationale": "y", "recommended_action": "z"}],
    }
    client = TestClient(api_main.app)
    with patch.object(translation, "translate_run", return_value=fake_translation) as mock_translate:
        resp1 = client.get(f"/runs/{run_id}/translation/fr")
        resp2 = client.get(f"/runs/{run_id}/translation/fr")

    assert resp1.status_code == 200
    assert resp1.json()["report_headline"] == "FR headline"
    assert resp2.status_code == 200
    assert mock_translate.call_count == 1  # second HTTP call was a cache read, not a new LLM call


def test_get_document_translation_route_rejects_unsupported_language(tmp_path, monkeypatch):
    import src.api.main as api_main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api_main, "DOCUMENTS_DIR", tmp_path)
    client = TestClient(api_main.app)
    resp = client.get("/documents/some-doc/translation/de")
    assert resp.status_code == 400


def test_get_document_translation_route_404s_on_unknown_document(tmp_path, monkeypatch):
    import src.api.main as api_main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api_main, "DOCUMENTS_DIR", tmp_path)
    client = TestClient(api_main.app)
    resp = client.get("/documents/does-not-exist/translation/ar")
    assert resp.status_code == 404


# ---------------------------------------------------------------------
# Chat assistant: lang -> language instruction, and /chat wiring
# ---------------------------------------------------------------------

def test_answer_question_includes_language_instruction_for_french(monkeypatch):
    from src.config import settings
    from src.services import chat_assistant

    monkeypatch.setattr(settings, "llm_api_key", "fake-key")
    monkeypatch.setattr(chat_assistant, "knowledge_base", MagicMock(retrieve=MagicMock(return_value=[])))

    captured = {}

    def fake_complete(prompt, primary_api_key):
        captured["prompt"] = prompt
        return {"answer": "Bonjour"}

    with patch.object(chat_assistant, "_complete_with_fallback", fake_complete):
        result = chat_assistant.answer_question(run=None, question="Quoi de neuf ?", lang="fr")

    assert result["answer"] == "Bonjour"
    assert "Respond in French" in captured["prompt"]


def test_answer_question_default_english_has_no_language_instruction(monkeypatch):
    from src.config import settings
    from src.services import chat_assistant

    monkeypatch.setattr(settings, "llm_api_key", "fake-key")
    monkeypatch.setattr(chat_assistant, "knowledge_base", MagicMock(retrieve=MagicMock(return_value=[])))

    captured = {}

    def fake_complete(prompt, primary_api_key):
        captured["prompt"] = prompt
        return {"answer": "Hi"}

    with patch.object(chat_assistant, "_complete_with_fallback", fake_complete):
        chat_assistant.answer_question(run=None, question="What's new?", lang="en")

    assert "Respond in French" not in captured["prompt"]
    assert "Respond in Modern Standard Arabic" not in captured["prompt"]


def test_chat_route_passes_lang_through_to_chat_assistant(monkeypatch):
    import src.api.main as api_main
    from fastapi.testclient import TestClient

    captured = {}

    def fake_answer_question(*, run, question, history, lang):
        captured["lang"] = lang
        return {"answer": "ok", "sources": []}

    monkeypatch.setattr(api_main.chat_assistant, "answer_question", fake_answer_question)
    client = TestClient(api_main.app)
    resp = client.post("/chat", json={"message": "hello", "run_id": None, "history": [], "lang": "ar"})

    assert resp.status_code == 200
    assert captured["lang"] == "ar"


def test_chat_route_defaults_lang_to_english_when_omitted(monkeypatch):
    import src.api.main as api_main
    from fastapi.testclient import TestClient

    captured = {}

    def fake_answer_question(*, run, question, history, lang):
        captured["lang"] = lang
        return {"answer": "ok", "sources": []}

    monkeypatch.setattr(api_main.chat_assistant, "answer_question", fake_answer_question)
    client = TestClient(api_main.app)
    resp = client.post("/chat", json={"message": "hello"})

    assert resp.status_code == 200
    assert captured["lang"] == "en"
