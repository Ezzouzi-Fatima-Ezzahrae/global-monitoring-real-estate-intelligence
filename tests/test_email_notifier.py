"""Tests for src/services/email_notifier.py.

_plain_text_body() and build_email_message() are pure/near-pure and tested
directly with real logic (real MIME structure, real attachment bytes) --
no network, no SMTP credentials required. send_email_report()'s actual
SMTP call is tested with smtplib.SMTP monkeypatched to a fake context
manager (same test-level dependency injection pattern documented in
tests/conftest.py) -- never a real network call.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.config import settings
from src.errors import MissingConfigurationError
from src.services import email_notifier


def _run(**report_overrides):
    report = {
        "report_date": "2026-09-11",
        "headline": "8 events collected; 1 flagged high real-estate relevance.",
        "top_events": [],
        "limitations": [],
        "no_significant_events": False,
    }
    report.update(report_overrides)
    return {"run_id": "r1", "run_date": "2026-09-11", "report": report, "events": [], "trace": []}


def test_plain_text_body_includes_headline_and_events():
    run = _run(top_events=[
        {"headline": "War escalates in region X", "source_name": "Global Political News Agent"},
    ])
    text = email_notifier._plain_text_body(run)
    assert "Orchid Island" in text
    assert "8 events collected" in text
    assert "War escalates in region X" in text
    assert "Full report attached as PDF." in text


def test_plain_text_body_truncates_beyond_max_events():
    events = [{"headline": f"Event {i}", "source_name": "Test"} for i in range(8)]
    run = _run(top_events=events)
    text = email_notifier._plain_text_body(run)
    assert "Event 0" in text and "Event 4" in text
    assert "Event 5" not in text
    assert "...and 3 more" in text


def test_plain_text_body_includes_limitations():
    run = _run(limitations=["RAG knowledge base (Phase 4) not yet implemented."])
    text = email_notifier._plain_text_body(run)
    assert "Confidence & limitations:" in text
    assert "RAG knowledge base (Phase 4) not yet implemented." in text


def test_plain_text_body_handles_no_significant_events():
    run = _run(no_significant_events=True)
    text = email_notifier._plain_text_body(run)
    assert "No significant events were found today" in text


def test_plain_text_body_handles_missing_report():
    run = {"run_id": "r1", "run_date": "2026-09-11", "report": None, "events": [],
           "trace": [{"agent": "Debate Stage", "status": "failed"}]}
    text = email_notifier._plain_text_body(run)
    assert "This run did not produce a report." in text
    assert "Debate Stage" in text


def test_build_email_message_has_real_subject_recipients_body_and_pdf_attachment(monkeypatch):
    monkeypatch.setattr(settings, "email_from", "bot@orchidisland.immo")
    monkeypatch.setattr(settings, "email_from_name", "Orchid Island - Intelligence Monitoring")
    monkeypatch.setattr(settings, "email_to", "team@orchidisland.immo,manager@orchidisland.immo")

    run = _run()
    pdf_bytes = b"%PDF-1.4 fake-but-real-bytes"
    msg = email_notifier.build_email_message(run, pdf_bytes)

    # Recipients see a real display name instead of the bare address --
    # EmailMessage re-serializes this in RFC 2822 "Name <addr>" form.
    assert msg["From"] == "Orchid Island - Intelligence Monitoring <bot@orchidisland.immo>"
    # EmailMessage's default policy re-serializes an address-list header with
    # a space after each comma -- a real, correct property of the stdlib
    # email package, not something send_email_report controls.
    assert msg["To"] == "team@orchidisland.immo, manager@orchidisland.immo"
    assert "2026-09-11" in msg["Subject"]
    assert "8 events collected" in msg["Subject"]

    body = msg.get_body(preferencelist=("plain",))
    assert "Full report attached as PDF." in body.get_content()

    attachments = list(msg.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_filename() == "orchid_island_digest_r1.pdf"
    assert attachments[0].get_content() == pdf_bytes


def test_build_email_message_falls_back_to_bare_address_when_no_display_name(monkeypatch):
    """EMAIL_FROM_NAME is optional -- an empty value must not produce a
    malformed header, it should behave exactly as it did before this
    feature existed."""
    monkeypatch.setattr(settings, "email_from", "bot@orchidisland.immo")
    monkeypatch.setattr(settings, "email_from_name", "")
    monkeypatch.setattr(settings, "email_to", "team@orchidisland.immo")

    msg = email_notifier.build_email_message(_run(), b"%PDF-1.4 fake")
    assert msg["From"] == "bot@orchidisland.immo"


def test_build_email_message_handles_missing_report_headline(monkeypatch):
    monkeypatch.setattr(settings, "email_from", "bot@orchidisland.immo")
    monkeypatch.setattr(settings, "email_to", "team@orchidisland.immo")
    run = {"run_id": "r2", "run_date": "2026-09-11", "report": None, "events": [], "trace": []}
    msg = email_notifier.build_email_message(run, b"%PDF-fake")
    assert "no report produced" in msg["Subject"]


def test_send_email_report_requires_smtp_credentials(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    with pytest.raises(MissingConfigurationError):
        email_notifier.send_email_report(_run(), b"%PDF-fake")


def test_send_email_report_requires_recipients(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_username", "user")
    monkeypatch.setattr(settings, "smtp_password", "pass")
    monkeypatch.setattr(settings, "email_from", "bot@orchidisland.immo")
    monkeypatch.setattr(settings, "email_to", "")
    with pytest.raises(MissingConfigurationError):
        email_notifier.send_email_report(_run(), b"%PDF-fake")


def test_send_email_report_sends_a_real_message_via_smtp(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", "user@test")
    monkeypatch.setattr(settings, "smtp_password", "secret")
    monkeypatch.setattr(settings, "email_from", "bot@orchidisland.immo")
    monkeypatch.setattr(settings, "email_to", "team@orchidisland.immo, manager@orchidisland.immo")

    calls = {"ehlo": 0, "starttls": 0, "login": None, "sent": None, "constructed_with": None}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls["constructed_with"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            calls["ehlo"] += 1

        def starttls(self):
            calls["starttls"] += 1

        def login(self, username, password):
            calls["login"] = (username, password)

        def send_message(self, msg, to_addrs=None):
            calls["sent"] = (msg, to_addrs)

    monkeypatch.setattr(email_notifier.smtplib, "SMTP", _FakeSMTP)

    result = email_notifier.send_email_report(_run(), b"%PDF-fake")

    assert result["sent_to"] == ["team@orchidisland.immo", "manager@orchidisland.immo"]
    assert calls["constructed_with"] == ("smtp.test", 587)
    assert calls["login"] == ("user@test", "secret")
    assert calls["starttls"] == 1
    sent_msg, sent_to_addrs = calls["sent"]
    assert sent_to_addrs == ["team@orchidisland.immo", "manager@orchidisland.immo"]
    assert list(sent_msg.iter_attachments())[0].get_content() == b"%PDF-fake"
