"""Tests for src/api/main.py — the local GUI's backend.

Uses FastAPI's TestClient (httpx under the hood, already a dependency) with
the same stub_* fixtures as the rest of the suite (see conftest.py's module
docstring) to stay offline. RUNS_DIR is redirected to a pytest tmp_path so
these tests never write into the project's real reports/runs/ folder.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import src.api.main as api_main
from src.config import settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)
    return TestClient(api_main.app)


def test_index_serves_the_local_gui(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Digest Console" in resp.text
    assert "/run-digest" in resp.text  # the page actually calls the real endpoint
    assert "/static/logo.png" in resp.text  # the header logo it references must be a real, servable path


def test_static_logo_and_favicon_assets_are_served(client):
    """The GUI's <link rel="icon"> and header <img> point at /static/* --
    confirm that mount actually serves the real files (src/api/static/*.png),
    not just that the HTML references them."""
    for path in ("/static/logo.png", "/static/favicon.png", "/static/favicon-180.png"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.headers["content-type"] == "image/png"
        assert len(resp.content) > 0


def test_health_reports_configured_credentials(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_api_key_configured"] is True
    assert body["groq_api_key_configured"] is True
    assert body["web_search_api_key_configured"] is True
    assert body["llm_provider"] == settings.llm_provider


def test_health_reports_missing_credential_honestly(client, monkeypatch):
    monkeypatch.setattr(settings, "web_search_api_key", "")
    resp = client.get("/health")
    assert resp.json()["web_search_api_key_configured"] is False


def test_run_digest_returns_real_structured_result_and_persists_it(client, stub_full_pipeline, tmp_path):
    resp = client.post("/run-digest")
    assert resp.status_code == 200
    body = resp.json()

    assert body["run_id"]
    assert body["trace"]
    assert all(step["agent"] for step in body["trace"])
    assert body["events"]
    assert body["report"]["headline"]
    assert "report_markdown" in body

    # Actually persisted to disk (redirected RUNS_DIR), not just returned.
    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    assert body["run_id"] in written[0].name


def test_run_digest_surfaces_missing_configuration_as_a_failed_trace_step(client, monkeypatch):
    """No mock fallback: a missing credential must show up as a real,
    labeled failure in the trace — never a silent empty report and never a
    500 that hides what's actually wrong."""
    monkeypatch.setattr(settings, "web_search_api_key", "")
    resp = client.post("/run-digest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["events"] == []
    assert any(step["status"] == "failed" and "WEB_SEARCH_API_KEY" in (step["error"] or "") for step in body["trace"])


def test_runs_list_is_empty_before_any_run(client):
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_runs_list_and_detail_reflect_a_real_persisted_run(client, stub_full_pipeline):
    run_id = client.post("/run-digest").json()["run_id"]

    listing = client.get("/runs").json()
    assert len(listing) == 1
    assert listing[0]["run_id"] == run_id
    assert listing[0]["event_count"] >= 1

    detail = client.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["run_id"] == run_id


def test_get_unknown_run_is_a_real_404(client):
    resp = client.get("/runs/does-not-exist")
    assert resp.status_code == 404


def test_get_run_pdf_is_a_real_downloadable_pdf(client, stub_full_pipeline):
    run_id = client.post("/run-digest").json()["run_id"]

    resp = client.get(f"/runs/{run_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert f'"orchid_island_digest_{run_id}.pdf"' in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")  # a real PDF, not a stub/placeholder


def test_get_pdf_for_unknown_run_is_a_real_404(client):
    resp = client.get("/runs/does-not-exist/pdf")
    assert resp.status_code == 404


def test_run_digest_creates_a_queryable_sqlite_index(client, stub_full_pipeline, tmp_path):
    client.post("/run-digest")
    assert (tmp_path / "index.db").exists()


def test_set_event_note_saves_and_the_run_detail_reflects_it(client, stub_full_pipeline):
    """The Digest Console's "place to ask questions" per event: save a note
    against a real event from a real run, then confirm GET /runs/{run_id}
    -- the same endpoint the GUI loads a run from -- actually shows it,
    since notes live on that same run JSON file rather than a separate
    store the GUI would need to know about."""
    run = client.post("/run-digest").json()
    run_id = run["run_id"]
    event_id = run["events"][0]["id"]

    resp = client.put(f"/runs/{run_id}/events/{event_id}/note", json={"text": "Is this confirmed by a second source?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["note"]["text"] == "Is this confirmed by a second source?"

    detail = client.get(f"/runs/{run_id}").json()
    assert detail["notes"][event_id]["text"] == "Is this confirmed by a second source?"


def test_set_event_note_with_blank_text_clears_it(client, stub_full_pipeline):
    run = client.post("/run-digest").json()
    run_id = run["run_id"]
    event_id = run["events"][0]["id"]

    client.put(f"/runs/{run_id}/events/{event_id}/note", json={"text": "First draft of a question."})
    resp = client.put(f"/runs/{run_id}/events/{event_id}/note", json={"text": "   "})
    assert resp.status_code == 200
    assert resp.json()["note"] is None

    detail = client.get(f"/runs/{run_id}").json()
    assert event_id not in detail.get("notes", {})


def test_set_event_note_for_unknown_run_is_a_real_404(client):
    resp = client.put("/runs/does-not-exist/events/e1/note", json={"text": "text"})
    assert resp.status_code == 404


def test_set_event_note_for_unknown_event_in_a_real_run_is_a_real_404(client, stub_full_pipeline):
    run_id = client.post("/run-digest").json()["run_id"]
    resp = client.put(f"/runs/{run_id}/events/not-a-real-event-id/note", json={"text": "text"})
    assert resp.status_code == 404


def test_runs_list_survives_and_backfills_preexisting_json_files(client, tmp_path):
    """A JSON run file written before this session's SQLite index existed
    (e.g. a project that already shipped with reports/runs/*.json) must
    still show up in GET /runs — real history is never silently dropped
    just because the index is new."""
    import json as _json

    preexisting = {
        "run_id": "20260910T120000Z-real01",
        "generated_at": "2026-09-10T12:00:00+00:00",
        "run_date": "2026-09-10",
        "events": [{"id": "e1"}],
        "trace": [],
        "report": {"headline": "Pre-existing real run", "no_significant_events": False},
    }
    (tmp_path / f"{preexisting['run_id']}.json").write_text(_json.dumps(preexisting), encoding="utf-8")

    listing = client.get("/runs").json()
    assert len(listing) == 1
    assert listing[0]["run_id"] == "20260910T120000Z-real01"
    assert listing[0]["headline"] == "Pre-existing real run"


def test_run_digest_and_notify_persists_the_run_and_honestly_skips_unconfigured_channels(client, stub_full_pipeline, tmp_path, monkeypatch):
    """No WhatsApp/SMTP credentials are configured -- both channels must
    report an honest skipped_reason, never a fabricated "sent", and the run
    itself must still be persisted exactly as POST /run-digest does.
    fake_credentials (conftest.py) only sets the LLM/search keys, but this
    explicitly blanks the notification fields too rather than relying on
    that -- a real .env on the machine running these tests can otherwise
    leak real values in and silently change what this test is exercising."""
    for field in ("callmebot_api_key", "twilio_account_sid", "twilio_auth_token",
                  "twilio_whatsapp_from", "whatsapp_to_numbers",
                  "smtp_host", "smtp_username", "smtp_password", "email_from", "email_to"):
        monkeypatch.setattr(settings, field, "")
    resp = client.post("/run-digest-and-notify")
    assert resp.status_code == 200
    body = resp.json()

    assert body["run_id"]
    assert body["report"]["headline"]
    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    assert body["run_id"] in written[0].name

    notifications = body["notifications"]
    assert notifications["whatsapp"]["sent_to"] == []
    assert "TWILIO" in notifications["whatsapp"]["skipped_reason"] or "not set" in notifications["whatsapp"]["skipped_reason"]
    assert notifications["email"]["sent_to"] == []
    assert "SMTP" in notifications["email"]["skipped_reason"] or "not set" in notifications["email"]["skipped_reason"]


def test_run_digest_and_notify_sends_for_real_when_credentials_are_configured(client, stub_full_pipeline, monkeypatch):
    """With both channels' credentials configured and their network calls
    stubbed (same test-level dependency injection as
    tests/test_whatsapp_notifier.py and tests/test_email_notifier.py), both
    channels must show a real "sent_to", built from this run's real report."""
    monkeypatch.setattr(settings, "whatsapp_provider", "twilio")
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest")
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")
    monkeypatch.setattr(settings, "twilio_whatsapp_from", "whatsapp:+14155238886")
    monkeypatch.setattr(settings, "whatsapp_to_numbers", "whatsapp:+212600000000")
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_username", "user@test")
    monkeypatch.setattr(settings, "smtp_password", "secret")
    monkeypatch.setattr(settings, "email_from", "bot@orchidisland.immo")
    monkeypatch.setattr(settings, "email_to", "team@orchidisland.immo")

    class _OKResponse:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(api_main.whatsapp_notifier.httpx, "post", lambda *a, **kw: _OKResponse())

    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, username, password):
            pass

        def send_message(self, msg, to_addrs=None):
            sent["to_addrs"] = to_addrs
            sent["msg"] = msg

    monkeypatch.setattr(api_main.email_notifier.smtplib, "SMTP", _FakeSMTP)

    resp = client.post("/run-digest-and-notify")
    assert resp.status_code == 200
    body = resp.json()

    assert body["notifications"]["whatsapp"]["sent_to"] == ["whatsapp:+212600000000"]
    assert body["notifications"]["whatsapp"]["failed"] == []
    assert body["notifications"]["email"]["sent_to"] == ["team@orchidisland.immo"]
    assert sent["to_addrs"] == ["team@orchidisland.immo"]
    assert list(sent["msg"].iter_attachments())[0].get_content_type() == "application/pdf"


def test_notify_test_endpoint_sends_a_clearly_labeled_test_message_without_running_the_pipeline(client, monkeypatch):
    """POST /notify/test must never run the real (potentially slow, real
    search + real LLM) pipeline -- it works with no stub_full_pipeline
    fixture at all, and still returns honest skipped_reason results when no
    notification credentials are configured (explicitly blanked here so a
    real .env on the machine running these tests can't leak real values in
    -- see the sibling test above for the same reasoning)."""
    for field in ("callmebot_api_key", "twilio_account_sid", "twilio_auth_token",
                  "twilio_whatsapp_from", "whatsapp_to_numbers",
                  "smtp_host", "smtp_username", "smtp_password", "email_from", "email_to"):
        monkeypatch.setattr(settings, field, "")
    resp = client.post("/notify/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["whatsapp"]["sent_to"] == []
    assert "skipped_reason" in body["whatsapp"]
    assert body["email"]["sent_to"] == []
    assert "skipped_reason" in body["email"]


def test_notify_test_message_is_labeled_as_a_test_not_a_real_report(client, monkeypatch):
    """Whatever text actually gets sent must say plainly that it's a
    connectivity test -- never something indistinguishable from a real
    daily report."""
    monkeypatch.setattr(settings, "whatsapp_provider", "twilio")
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest")
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")
    monkeypatch.setattr(settings, "twilio_whatsapp_from", "whatsapp:+14155238886")
    monkeypatch.setattr(settings, "whatsapp_to_numbers", "whatsapp:+212600000000")

    captured = {}

    class _OKResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, auth=None, data=None, timeout=None):
        captured["body"] = data["Body"]
        return _OKResponse()

    monkeypatch.setattr(api_main.whatsapp_notifier.httpx, "post", fake_post)

    resp = client.post("/notify/test")
    assert resp.status_code == 200
    assert "CONNECTIVITY TEST" in captured["body"] or "connectivity test" in captured["body"].lower()


def test_chat_requires_llm_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    resp = client.post("/chat", json={"message": "What happened today?"})
    assert resp.status_code == 503
    assert "LLM_API_KEY" in resp.json()["detail"]


def test_chat_answers_with_no_run_loaded(client, monkeypatch):
    from src.services import chat_assistant, knowledge_base
    from src.services.llm_client import llm_client as llm_client_instance

    monkeypatch.setattr(knowledge_base, "retrieve", lambda query, top_k=4, min_score=0.05: [])
    monkeypatch.setattr(
        llm_client_instance,
        "complete_json",
        lambda **kwargs: {"answer": "No report is loaded yet, so I can't answer that from today's events."},
    )

    resp = client.post("/chat", json={"message": "What's the biggest risk today?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "No report is loaded yet, so I can't answer that from today's events."
    assert body["sources"] == []


def test_chat_grounds_its_answer_in_the_loaded_run(client, monkeypatch, tmp_path):
    from src.services import knowledge_base
    from src.services.llm_client import llm_client as llm_client_instance

    monkeypatch.setattr(knowledge_base, "retrieve", lambda query, top_k=4, min_score=0.05: [])

    run_id = "20260916T090000Z-test01"
    run_payload = {
        "run_id": run_id,
        "run_date": "2026-09-16",
        "events": [
            {
                "id": "e1",
                "agent": "Real Estate Sector Agent",
                "headline": "Villa demand holds steady in Palmeraie",
                "summary": "Listings data shows no major change in asking prices this month.",
                "sentiment": "neutral",
                "relevance_to_real_estate": "high",
                "source_name": "Test Source",
            }
        ],
        "report": {"headline": "A steady week for Marrakech villas.", "impact_analysis": []},
    }
    (tmp_path / f"{run_id}.json").write_text(__import__("json").dumps(run_payload), encoding="utf-8")

    captured = {}

    def fake_complete_json(*, provider, model, api_key, prompt):
        captured["prompt"] = prompt
        return {"answer": "Palmeraie villa demand is steady this month."}

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    resp = client.post("/chat", json={"message": "How is Palmeraie doing?", "run_id": run_id})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Palmeraie villa demand is steady this month."
    assert "Villa demand holds steady in Palmeraie" in captured["prompt"]


def test_chat_with_unknown_run_id_still_answers_from_knowledge_base_only(client, monkeypatch):
    from src.services import knowledge_base
    from src.services.llm_client import llm_client as llm_client_instance

    monkeypatch.setattr(knowledge_base, "retrieve", lambda query, top_k=4, min_score=0.05: [])
    captured = {}

    def fake_complete_json(*, provider, model, api_key, prompt):
        captured["prompt"] = prompt
        return {"answer": "I don't have a report loaded for that run."}

    monkeypatch.setattr(llm_client_instance, "complete_json", fake_complete_json)

    resp = client.post("/chat", json={"message": "Anything new?", "run_id": "does-not-exist"})
    assert resp.status_code == 200
    assert "No daily report is currently loaded" in captured["prompt"]
