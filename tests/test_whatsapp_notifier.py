"""Tests for src/services/whatsapp_notifier.py.

build_whatsapp_text() is pure and tested directly with real logic, no
credentials needed. send_whatsapp_report()'s actual provider calls (Twilio
via httpx.post, callmebot via httpx.get) are tested with those functions
monkeypatched (same test-level dependency injection pattern documented in
tests/conftest.py) -- never a real network call.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.config import settings
from src.errors import MissingConfigurationError
from src.services import whatsapp_notifier


def _run(**report_overrides):
    report = {
        "report_date": "2026-09-11",
        "headline": "8 events collected; 1 flagged high real-estate relevance.",
        "top_events": [],
        "debate_highlights": [],
        "no_significant_events": False,
    }
    report.update(report_overrides)
    return {"run_id": "r1", "run_date": "2026-09-11", "report": report, "events": [], "trace": []}


def test_build_whatsapp_text_includes_headline_and_events():
    run = _run(top_events=[
        {"headline": "War escalates in region X", "relevance_to_real_estate": "high"},
        {"headline": "Minor local news", "relevance_to_real_estate": "low"},
    ])
    text = whatsapp_notifier.build_whatsapp_text(run)
    assert "8 events collected" in text
    assert "War escalates in region X" in text
    assert "🔴" in text  # high relevance flagged
    assert "Full report + PDF: sent by email." in text


def test_build_whatsapp_text_truncates_beyond_max_events():
    events = [{"headline": f"Event {i}", "relevance_to_real_estate": "low"} for i in range(5)]
    run = _run(top_events=events)
    text = whatsapp_notifier.build_whatsapp_text(run)
    assert "Event 0" in text and "Event 1" in text and "Event 2" in text
    assert "Event 4" not in text
    assert "2 more in the full report" in text


def test_build_whatsapp_text_flags_contested_events():
    run = _run(debate_highlights=["[RESOLVED] fine", "[CONTESTED] disputed claim"])
    text = whatsapp_notifier.build_whatsapp_text(run)
    assert "1 event(s) contested/uncertain" in text


def test_build_whatsapp_text_handles_no_significant_events():
    run = _run(no_significant_events=True)
    text = whatsapp_notifier.build_whatsapp_text(run)
    assert "No significant events today." in text


def test_build_whatsapp_text_handles_missing_report():
    run = {"run_id": "r1", "run_date": "2026-09-11", "report": None, "events": [], "trace": [{"agent": "Debate Stage", "status": "failed"}]}
    text = whatsapp_notifier.build_whatsapp_text(run)
    assert "did not produce a report" in text
    assert "Debate Stage" in text


def test_send_whatsapp_report_requires_recipients(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_to_numbers", "")
    with pytest.raises(MissingConfigurationError):
        whatsapp_notifier.send_whatsapp_report(_run())


def test_send_whatsapp_report_calls_twilio_for_each_recipient(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "twilio")
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest")
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")
    monkeypatch.setattr(settings, "twilio_whatsapp_from", "whatsapp:+14155238886")
    monkeypatch.setattr(settings, "whatsapp_to_numbers", "whatsapp:+212600000001, whatsapp:+212600000002")

    calls = []

    class _FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, auth=None, data=None, timeout=None):
        calls.append({"url": url, "auth": auth, "data": data})
        return _FakeResponse()

    monkeypatch.setattr(whatsapp_notifier.httpx, "post", fake_post)

    result = whatsapp_notifier.send_whatsapp_report(_run())
    assert result["sent_to"] == ["whatsapp:+212600000001", "whatsapp:+212600000002"]
    assert result["failed"] == []
    assert len(calls) == 2
    assert calls[0]["auth"] == ("ACtest", "test-token")
    assert calls[0]["data"]["From"] == "whatsapp:+14155238886"
    assert "8 events collected" in calls[0]["data"]["Body"]


def test_send_whatsapp_report_collects_per_recipient_failures_without_raising(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "twilio")
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest")
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")
    monkeypatch.setattr(settings, "twilio_whatsapp_from", "whatsapp:+14155238886")
    monkeypatch.setattr(settings, "whatsapp_to_numbers", "whatsapp:+212600000001,whatsapp:+212600000002")

    def fake_post(url, auth=None, data=None, timeout=None):
        if data["To"] == "whatsapp:+212600000001":
            raise RuntimeError("63016: recipient has not joined the sandbox")

        class _OK:
            def raise_for_status(self):
                pass
        return _OK()

    monkeypatch.setattr(whatsapp_notifier.httpx, "post", fake_post)

    result = whatsapp_notifier.send_whatsapp_report(_run())
    assert result["sent_to"] == ["whatsapp:+212600000002"]
    assert len(result["failed"]) == 1
    assert result["failed"][0]["to"] == "whatsapp:+212600000001"


# --- callmebot provider (added 2026-09-14, at Orchid Island's request as a
# free alternative to Twilio) ---------------------------------------------

def test_send_whatsapp_report_requires_callmebot_api_key_when_selected(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "callmebot")
    monkeypatch.setattr(settings, "callmebot_api_key", "")
    monkeypatch.setattr(settings, "whatsapp_to_numbers", "+212600000001")
    with pytest.raises(MissingConfigurationError, match="CALLMEBOT_API_KEY"):
        whatsapp_notifier.send_whatsapp_report(_run())


def test_send_whatsapp_report_calls_callmebot_for_each_recipient(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "callmebot")
    monkeypatch.setattr(settings, "callmebot_api_key", "test-apikey")
    monkeypatch.setattr(settings, "whatsapp_to_numbers", "+212600000001, +212600000002")

    calls = []

    class _FakeResponse:
        text = "message queued"

        def raise_for_status(self):
            pass

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params})
        return _FakeResponse()

    monkeypatch.setattr(whatsapp_notifier.httpx, "get", fake_get)

    result = whatsapp_notifier.send_whatsapp_report(_run())
    assert result["sent_to"] == ["+212600000001", "+212600000002"]
    assert result["failed"] == []
    assert len(calls) == 2
    assert calls[0]["url"] == whatsapp_notifier.CALLMEBOT_API_BASE
    assert calls[0]["params"]["phone"] == "+212600000001"
    assert calls[0]["params"]["apikey"] == "test-apikey"
    assert "8 events collected" in calls[0]["params"]["text"]


def test_callmebot_strips_whatsapp_prefix_from_numbers(monkeypatch):
    """A recipient number left over in "whatsapp:+212..." format (the
    Twilio convention) must still reach callmebot as a plain number --
    callmebot doesn't understand the "whatsapp:" prefix."""
    monkeypatch.setattr(settings, "whatsapp_provider", "callmebot")
    monkeypatch.setattr(settings, "callmebot_api_key", "test-apikey")
    monkeypatch.setattr(settings, "whatsapp_to_numbers", "whatsapp:+212600000001")

    calls = []

    class _FakeResponse:
        text = "ok"

        def raise_for_status(self):
            pass

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return _FakeResponse()

    monkeypatch.setattr(whatsapp_notifier.httpx, "get", fake_get)

    result = whatsapp_notifier.send_whatsapp_report(_run())
    assert calls[0]["phone"] == "+212600000001"
    assert result["sent_to"] == ["whatsapp:+212600000001"]  # reported as configured, for traceability


def test_unrecognized_whatsapp_provider_raises_missing_configuration_error(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "sms-carrier-pigeon")
    monkeypatch.setattr(settings, "whatsapp_to_numbers", "+212600000001")
    with pytest.raises(MissingConfigurationError, match="sms-carrier-pigeon"):
        whatsapp_notifier.send_whatsapp_report(_run())
