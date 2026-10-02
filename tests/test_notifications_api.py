"""Tests for src/api/main.py's _attempt_notifications / POST /notify/test
covering the 2026-09-21 addition of Telegram as a third channel alongside
WhatsApp and email. Confirms the three channels are independent (one
missing credential's honest skip doesn't affect the others) the same way
this project already guarantees for WhatsApp + email."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import src.api.main as api_main


def test_notify_test_reports_all_three_channels_honestly_skipped_with_nothing_configured(monkeypatch):
    from src.config import settings

    for field in (
        "twilio_account_sid", "twilio_auth_token", "twilio_whatsapp_from", "callmebot_api_key",
        "whatsapp_to_numbers", "telegram_bot_token", "telegram_chat_ids",
        "smtp_host", "smtp_username", "smtp_password", "email_from", "email_to",
    ):
        monkeypatch.setattr(settings, field, "")

    client = TestClient(api_main.app)
    resp = client.post("/notify/test")
    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) == {"whatsapp", "telegram", "email"}
    for channel in ("whatsapp", "telegram", "email"):
        assert body[channel]["sent_to"] == []
        assert "skipped_reason" in body[channel]


def test_notify_test_sends_a_real_telegram_message_when_configured_leaving_others_skipped(monkeypatch):
    from src.config import settings
    from unittest.mock import patch

    for field in (
        "twilio_account_sid", "twilio_auth_token", "twilio_whatsapp_from", "callmebot_api_key",
        "whatsapp_to_numbers", "smtp_host", "smtp_username", "smtp_password", "email_from", "email_to",
    ):
        monkeypatch.setattr(settings, field, "")
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_chat_ids", "12345")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    client = TestClient(api_main.app)
    with patch("httpx.post", return_value=FakeResponse()) as mock_post:
        resp = client.post("/notify/test")

    body = resp.json()
    assert body["telegram"]["sent_to"] == ["12345"]
    assert "skipped_reason" in body["whatsapp"]
    assert "skipped_reason" in body["email"]
    assert mock_post.call_count == 1
    assert "fake-token" in mock_post.call_args.args[0]


def test_notify_status_reports_all_three_channels_not_configured_with_nothing_set(monkeypatch):
    """2026-09-22 addition: GET /notify/status backs the Alerts page's
    per-channel "Configured"/"Not configured" chips. Must read the exact
    same fields _attempt_notifications actually needs (see the two tests
    above), never a looser or stricter check, so the chip can't disagree
    with what a real send would do."""
    from src.config import settings

    for field in (
        "twilio_account_sid", "twilio_auth_token", "twilio_whatsapp_from", "callmebot_api_key",
        "whatsapp_to_numbers", "telegram_bot_token", "telegram_chat_ids",
        "smtp_host", "smtp_username", "smtp_password", "email_from", "email_to",
    ):
        monkeypatch.setattr(settings, field, "")

    client = TestClient(api_main.app)
    resp = client.get("/notify/status")
    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) == {"whatsapp", "telegram", "email"}
    assert body["whatsapp"]["configured"] is False
    assert body["telegram"]["configured"] is False
    assert body["email"]["configured"] is False
    # No secret values are ever echoed back, only booleans/provider name.
    assert body["whatsapp"] == {"configured": False, "provider": settings.whatsapp_provider}


def test_notify_status_reports_telegram_configured_when_credentials_present(monkeypatch):
    from src.config import settings

    for field in (
        "twilio_account_sid", "twilio_auth_token", "twilio_whatsapp_from", "callmebot_api_key",
        "whatsapp_to_numbers", "smtp_host", "smtp_username", "smtp_password", "email_from", "email_to",
    ):
        monkeypatch.setattr(settings, field, "")
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_chat_ids", "12345")

    client = TestClient(api_main.app)
    resp = client.get("/notify/status")
    body = resp.json()

    assert body["telegram"]["configured"] is True
    assert body["whatsapp"]["configured"] is False
    assert body["email"]["configured"] is False
