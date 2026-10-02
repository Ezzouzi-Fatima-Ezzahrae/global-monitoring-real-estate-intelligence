"""Email notification for a run's report (2026-09-11 addition, added at
Orchid Island's request to notify the company by email each day).

Uses plain SMTP via Python's standard library (`smtplib` + `email`) --
zero new dependency, and works with literally any provider (Gmail with an
app password, Office 365, a company mail server, or a transactional
service like SendGrid/Mailgun's SMTP relay) by just changing .env, the
same provider-swappable spirit as LLM_PROVIDER in src/config/settings.py.

No mock mode: sending requires real, configured credentials (SMTP_HOST,
SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM, EMAIL_TO in .env) and raises
MissingConfigurationError immediately if they aren't set. Like
whatsapp_notifier.py, this is an OPTIONAL channel -- the callers
(POST /run-digest-and-notify, scripts/daily_notify.py) catch that specific
error and report the channel as honestly skipped rather than failing the
whole run.

The real PDF (src/services/pdf_export.py) is attached directly -- unlike
WhatsApp (see that module's docstring for why), email attachments need no
public hosting, so this channel is what actually carries the full report.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from src.config import settings

_MAX_EVENTS_IN_BODY = 5


def _plain_text_body(run: dict) -> str:
    """Pure, fully-testable function: the email body text (the PDF
    attachment, built separately by pdf_export.py, carries the full
    report)."""
    report = run.get("report") or {}
    run_date = report.get("report_date") or run.get("run_date", "")
    lines = [f"Orchid Island — Daily Intelligence Digest ({run_date})", ""]

    if not report:
        failed = [s.get("agent") for s in run.get("trace", []) if s.get("status") == "failed"]
        lines.append("This run did not produce a report.")
        if failed:
            lines.append(f"Failed step(s): {', '.join(failed)}.")
        lines.append("")
        lines.append("See the pipeline trace in the Digest Console for full details.")
        return "\n".join(lines)

    lines.append(report.get("headline", ""))
    lines.append("")

    if report.get("no_significant_events"):
        lines.append("No significant events were found today that warrant a notable update.")
    else:
        events = report.get("top_events") or run.get("events") or []
        if events:
            lines.append("Top events:")
            for e in events[:_MAX_EVENTS_IN_BODY]:
                lines.append(f"- {e.get('headline', '')} ({e.get('source_name') or e.get('source_url', '')})")
            if len(events) > _MAX_EVENTS_IN_BODY:
                lines.append(f"...and {len(events) - _MAX_EVENTS_IN_BODY} more — see the attached PDF.")
            lines.append("")

        limitations = report.get("limitations") or []
        if limitations:
            lines.append("Confidence & limitations:")
            for l in limitations:
                lines.append(f"- {l}")
            lines.append("")

    lines.append("Full report attached as PDF.")
    lines.append("— Sent automatically by the Global Monitoring & Real Estate Intelligence System")
    return "\n".join(lines)


def build_email_message(run: dict, pdf_bytes: bytes) -> EmailMessage:
    """Builds the real MIME message (subject, plain-text body, PDF
    attachment) without sending anything -- kept separate from
    send_email_report() specifically so this can be verified directly in
    tests (real MIME structure, real attachment bytes) with no network and
    no SMTP credentials required."""
    report = run.get("report") or {}
    run_date = report.get("report_date") or run.get("run_date", "")
    headline = report.get("headline") or "no report produced"

    msg = EmailMessage()
    msg["Subject"] = f"Orchid Island Daily Digest — {run_date}: {headline}"[:250]
    # A display name (EMAIL_FROM_NAME, e.g. "Orchid Island - Intelligence
    # Monitoring") is what an inbox actually shows instead of the raw
    # address -- formataddr builds the correct "Name <address>" header
    # form (and quotes/escapes the name if it ever needs it) rather than
    # string-concatenating it by hand. An empty EMAIL_FROM_NAME falls back
    # to the bare address, unchanged from before this existed.
    msg["From"] = formataddr((settings.email_from_name, settings.email_from)) if settings.email_from_name else settings.email_from
    msg["To"] = settings.email_to
    msg.set_content(_plain_text_body(run))

    run_id = run.get("run_id", "report")
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=f"orchid_island_digest_{run_id}.pdf",
    )
    return msg


def send_email_report(run: dict, pdf_bytes: bytes) -> dict:
    """Sends one real email, with the run's real PDF attached, to every
    address in EMAIL_TO (comma-separated). Raises MissingConfigurationError
    if any required setting is missing -- the caller decides whether that's
    a hard failure or an honest skip (see module docstring)."""
    host = settings.require("smtp_host", "SMTP_HOST")
    username = settings.require("smtp_username", "SMTP_USERNAME")
    password = settings.require("smtp_password", "SMTP_PASSWORD")
    settings.require("email_from", "EMAIL_FROM")
    raw_to = settings.require("email_to", "EMAIL_TO")
    recipients = [addr.strip() for addr in raw_to.split(",") if addr.strip()]

    msg = build_email_message(run, pdf_bytes)

    with smtplib.SMTP(host, settings.smtp_port, timeout=settings.request_timeout_seconds) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(username, password)
        server.send_message(msg, to_addrs=recipients)

    return {"sent_to": recipients}
