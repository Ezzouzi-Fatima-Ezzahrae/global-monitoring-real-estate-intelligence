"""WhatsApp notification for a run's report (2026-09-11 addition, added at
Orchid Island's request: "send a WhatsApp message ... to notify them each
day").

Two providers, switched by WHATSAPP_PROVIDER in .env (src/config/settings.py):

- "twilio" (the original implementation): Twilio's WhatsApp API directly
  over REST (via httpx, no Twilio SDK dependency). Free WhatsApp Sandbox to
  start sending today, but real per-message cost beyond that -- Twilio's
  own pricing, not fixed by this system.
- "callmebot" (added 2026-09-14, at Orchid Island's request, after Twilio's
  cost didn't work for them): callmebot.com's free personal-use WhatsApp
  API. No monthly cost, no Meta Business verification -- but each
  recipient must opt in once (add the bot's number as a WhatsApp contact
  and send it the exact phrase "I allow callmebot to send me messages";
  see README "Daily automatic notifications" for the full walkthrough and
  why the bot's number isn't hardcoded here).

Both are plain REST calls, the same pattern this project already uses for
Gemini, Groq, and Tavily in src/services/llm_client.py and
src/tools/web_search.py. Meta's own WhatsApp Cloud API remains a documented
third option if you'd rather use that later -- it would mean adding a
third _send_via_* function below, not changing the calling code.

No mock mode: sending requires real, configured credentials for whichever
provider is selected (see _send_via_twilio / _send_via_callmebot below) and
WHATSAPP_TO_NUMBERS. Missing credentials raise MissingConfigurationError
immediately, same as every other integration in this project -- this is an
OPTIONAL channel, though: src/api/main.py's POST /run-digest-and-notify and
scripts/daily_notify.py both catch that specific error and report the
channel as honestly skipped, rather than failing the whole run over a
notification channel not being set up yet.

Real technical constraint worth knowing (not worked around, stated
honestly): neither provider can attach the PDF report itself here. Twilio
can only attach *media* to a WhatsApp message via a public URL it fetches
itself, and callmebot's API is text-only -- and since this system runs
entirely locally with nothing hosted publicly, there's no URL to give
either one. The WhatsApp message is a concise TEXT digest (headline + top
events); the full PDF report goes out over email instead (see
src/services/email_notifier.py), which handles real attachments natively.
"""
from __future__ import annotations

import logging

import httpx

from src.config import settings
from src.errors import MissingConfigurationError

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/Accounts"
CALLMEBOT_API_BASE = "https://api.callmebot.com/whatsapp.php"
_MAX_EVENTS_IN_MESSAGE = 3
_WHATSAPP_BODY_CHAR_LIMIT = 1550  # Twilio's practical WhatsApp body limit is ~1600 chars


def _relevance_flag(event: dict) -> str:
    rel = (event.get("relevance_to_real_estate") or "").lower()
    return "🔴" if rel == "high" else ("🟠" if rel == "medium" else "")


def build_whatsapp_text(run: dict) -> str:
    """Pure, fully-testable function: turns one run dict (the same shape
    src/api/main.py serializes) into the WhatsApp message text. No network,
    no side effects -- exercised directly in tests/test_whatsapp_notifier.py
    without needing any real credentials."""
    report = run.get("report") or {}
    run_date = report.get("report_date") or run.get("run_date", "")
    lines = [f"*Orchid Island — Daily Digest ({run_date})*"]

    if not report:
        failed = [s.get("agent") for s in run.get("trace", []) if s.get("status") == "failed"]
        lines.append("This run did not produce a report.")
        if failed:
            lines.append(f"Failed step(s): {', '.join(failed)}.")
        return "\n".join(lines)

    lines.append(report.get("headline", ""))

    if report.get("no_significant_events"):
        lines.append("\nNo significant events today.")
        return "\n".join(lines)

    events = report.get("top_events") or run.get("events") or []
    if events:
        lines.append("\n*Top events:*")
        for e in events[:_MAX_EVENTS_IN_MESSAGE]:
            flag = _relevance_flag(e)
            headline = e.get("headline", "")
            lines.append(f"{flag} {headline}".strip())
        if len(events) > _MAX_EVENTS_IN_MESSAGE:
            lines.append(f"…and {len(events) - _MAX_EVENTS_IN_MESSAGE} more in the full report.")

    debate = report.get("debate_highlights") or []
    contested = [d for d in debate if d.upper().startswith("[CONTESTED") or d.upper().startswith("[UNCERTAIN")]
    if contested:
        lines.append(f"\n⚠ {len(contested)} event(s) contested/uncertain in debate — see full report.")

    lines.append("\nFull report + PDF: sent by email.")
    text = "\n".join(lines)
    if len(text) > _WHATSAPP_BODY_CHAR_LIMIT:
        text = text[: _WHATSAPP_BODY_CHAR_LIMIT - 1] + "…"
    return text


def _send_via_twilio(to_number: str, body: str) -> None:
    account_sid = settings.require("twilio_account_sid", "TWILIO_ACCOUNT_SID")
    auth_token = settings.require("twilio_auth_token", "TWILIO_AUTH_TOKEN")
    from_number = settings.require("twilio_whatsapp_from", "TWILIO_WHATSAPP_FROM")

    resp = httpx.post(
        f"{TWILIO_API_BASE}/{account_sid}/Messages.json",
        auth=(account_sid, auth_token),
        data={"To": to_number, "From": from_number, "Body": body},
        timeout=settings.request_timeout_seconds,
    )
    resp.raise_for_status()


def _send_via_callmebot(to_number: str, body: str) -> None:
    """callmebot.com's free WhatsApp API -- see module docstring for why
    this exists. `to_number` may come in with a "whatsapp:" prefix (the
    Twilio convention some recipients may already be entered with in
    WHATSAPP_TO_NUMBERS) -- stripped here since callmebot expects a plain
    "+<countrycode><number>" phone number.

    callmebot's docs don't specify an error response shape (no documented
    status codes or error body format for a wrong API key / a recipient
    who hasn't opted in yet), so this can only check what's actually
    checkable: a non-2xx HTTP status raises via raise_for_status(). A
    genuine send failure that still returns HTTP 200 (e.g. a stale API
    key) won't be caught here -- if a message doesn't actually arrive
    despite this reporting success, check the WhatsApp thread with the
    callmebot bot number directly, it often explains what went wrong
    there."""
    api_key = settings.require("callmebot_api_key", "CALLMEBOT_API_KEY")
    plain_number = to_number.replace("whatsapp:", "").strip()

    resp = httpx.get(
        CALLMEBOT_API_BASE,
        params={"phone": plain_number, "text": body, "apikey": api_key},
        timeout=settings.request_timeout_seconds,
    )
    resp.raise_for_status()


def _send_one(to_number: str, body: str) -> None:
    """Dispatches to whichever provider WHATSAPP_PROVIDER selects. An
    unrecognized value is treated the same as a missing credential -- a
    real configuration problem that should stop the run loudly (FR-13),
    not be silently skipped or defaulted to a guess."""
    provider = (settings.whatsapp_provider or "twilio").strip().lower()
    if provider == "twilio":
        _send_via_twilio(to_number, body)
    elif provider == "callmebot":
        _send_via_callmebot(to_number, body)
    else:
        raise MissingConfigurationError(
            f"WHATSAPP_PROVIDER is set to {settings.whatsapp_provider!r} in .env, which this system "
            "doesn't recognize -- set it to 'twilio' or 'callmebot'."
        )


def send_whatsapp_report(run: dict) -> dict:
    """Sends the WhatsApp digest to every configured recipient, via
    whichever provider WHATSAPP_PROVIDER selects (see _send_one above).
    Raises MissingConfigurationError if WHATSAPP_TO_NUMBERS (or that
    provider's own credentials) isn't set — the caller decides whether
    that's a hard failure or an honest skip (see module docstring).
    A per-recipient send failure (e.g. a number that hasn't joined a
    Twilio Sandbox yet) is NOT raised — it's collected in `failed` so one
    bad number doesn't stop the others, the same fail-gracefully principle
    this project already applies to web_search/fetch_page."""
    raw_numbers = settings.require("whatsapp_to_numbers", "WHATSAPP_TO_NUMBERS")
    numbers = [n.strip() for n in raw_numbers.split(",") if n.strip()]

    body = build_whatsapp_text(run)
    sent_to: list[str] = []
    failed: list[dict] = []
    for number in numbers:
        try:
            _send_one(number, body)
            sent_to.append(number)
        except MissingConfigurationError:
            raise  # a real config problem, not a per-recipient issue -- let it propagate
        except Exception as exc:
            logger.error("WhatsApp send failed for %s: %s", number, exc)
            failed.append({"to": number, "error": str(exc)})

    return {"sent_to": sent_to, "failed": failed, "message_body": body}
