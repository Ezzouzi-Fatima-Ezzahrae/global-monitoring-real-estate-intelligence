"""Tests for src/services/telegram_notifier.py (2026-09-21 addition, at
Orchid Island's request: "automation with telegram"). Mirrors the shape of
the existing WhatsApp/email notifier tests referenced in those modules'
own docstrings: build_telegram_text is pure and fully-testable with no
network, and send_telegram_report's real HTTP call is stubbed via
monkeypatch/mock rather than hitting the real Telegram API.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

from src.config import settings
from src.errors import MissingConfigurationError
from src.services.telegram_notifier import build_telegram_text, send_telegram_report


def _run(**report_overrides) -> dict:
    report = {
        "report_date": "2026-09-21",
        "headline": "3 events collected across 2 sources; 2 flagged medium/high relevance.",
        "top_events": [
            {"headline": "High-relevance event", "relevance_to_real_estate": "high", "priority_rank": 1},
            {"headline": "Medium-relevance event", "relevance_to_real_estate": "medium", "priority_rank": 2},
            {"headline": "Another event", "relevance_to_real_estate": "medium", "priority_rank": 3},
        ],
        "no_significant_events": False,
        "debate_highlights": [],
    }
    report.update(report_overrides)
    return {"run_date": "2026-09-21", "report": report, "events": [], "trace": []}


def test_build_telegram_text_includes_headline_and_ranked_events():
    text = build_telegram_text(_run())
    assert "3 events collected" in text
    assert "#1 High-relevance event" in text
    assert "#2 Medium-relevance event" in text
    assert "🔴" in text  # high relevance flag
    assert "🟠" in text  # medium relevance flag


def test_build_telegram_text_escapes_html_special_characters():
    """Telegram's HTML parse mode breaks on a raw '<', '>' or '&' in the
    message -- a real headline containing any of these must not corrupt
    the message's formatting or get silently dropped by Telegram."""
    run = _run(headline="Prices <up> & demand rising")
    run["report"]["top_events"] = [
        {"headline": "A & B < C report", "relevance_to_real_estate": "high", "priority_rank": 1}
    ]
    text = build_telegram_text(run)
    assert "<up>" not in text
    assert "&lt;up&gt;" in text
    assert "A &amp; B &lt; C report" in text


def test_build_telegram_text_reports_no_significant_events_honestly():
    run = _run(no_significant_events=True, top_events=[])
    text = build_telegram_text(run)
    assert "No significant events today" in text


def test_build_telegram_text_handles_a_run_with_no_report():
    run = {"run_date": "2026-09-21", "report": None, "trace": [{"agent": "X", "status": "failed"}]}
    text = build_telegram_text(run)
    assert "did not produce a report" in text
    assert "X" in text


def test_build_telegram_text_truncates_to_telegram_char_limit():
    run = _run()
    run["report"]["top_events"] = [
        {"headline": "Y" * 500, "relevance_to_real_estate": "high", "priority_rank": i} for i in range(1, 20)
    ]
    text = build_telegram_text(run)
    assert len(text) <= 4000


def test_send_telegram_report_requires_bot_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_ids", "111111")
    with pytest.raises(MissingConfigurationError, match="TELEGRAM_BOT_TOKEN"):
        send_telegram_report(_run())


def test_send_telegram_report_requires_chat_ids(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_chat_ids", "")
    with pytest.raises(MissingConfigurationError, match="TELEGRAM_CHAT_IDS"):
        send_telegram_report(_run())


def test_send_telegram_report_sends_to_every_configured_chat_id(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_chat_ids", "111,222")

    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_post(url, json, timeout):
        calls.append((url, json["chat_id"]))
        return FakeResponse()

    with patch("httpx.post", side_effect=fake_post):
        result = send_telegram_report(_run())

    assert result["sent_to"] == ["111", "222"]
    assert result["failed"] == []
    assert len(calls) == 2
    assert all("fake-token" in url for url, _ in calls)


def test_send_telegram_report_collects_per_recipient_failures_without_raising(monkeypatch):
    """One chat id that hasn't started a conversation with the bot (a real
    Telegram constraint) must not stop the digest going to the others."""
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_chat_ids", "111,222")

    class FakeResponse:
        def __init__(self, ok, description=None):
            self._ok = ok
            self._description = description

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": self._ok, "description": self._description}

    def fake_post(url, json, timeout):
        if json["chat_id"] == "111":
            return FakeResponse(ok=False, description="Forbidden: bot was blocked by the user")
        return FakeResponse(ok=True)

    with patch("httpx.post", side_effect=fake_post):
        result = send_telegram_report(_run())

    assert result["sent_to"] == ["222"]
    assert len(result["failed"]) == 1
    assert result["failed"][0]["to"] == "111"
    assert "blocked" in result["failed"][0]["error"]


def test_send_telegram_report_raises_a_real_http_error_status_as_a_per_recipient_failure(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_chat_ids", "111")

    def fake_post(url, json, timeout):
        request = httpx.Request("POST", url)
        response = httpx.Response(status_code=404, request=request, json={"ok": False, "description": "chat not found"})
        raise httpx.HTTPStatusError("Not Found", request=request, response=response)

    with patch("httpx.post", side_effect=fake_post):
        result = send_telegram_report(_run())

    assert result["sent_to"] == []
    assert len(result["failed"]) == 1
