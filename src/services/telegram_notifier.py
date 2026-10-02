"""Telegram notification for a run's report (2026-09-21 addition, at
Orchid Island's request: "i want to added automation with telegram").
Same daily digest as WhatsApp and email (src/services/whatsapp_notifier.py,
src/services/email_notifier.py) — one more channel wired into the same
POST /run-digest-and-notify and scripts/daily_notify.py, sent
automatically once a day alongside the others.

Unlike WhatsApp, there's only one real provider here: Telegram's own Bot
API is free (no per-message cost, no business verification, no sandbox
opt-in dance) — see README.md "Daily automatic notifications" for how to
create a bot with @BotFather and find your chat id. Plain REST via httpx,
same pattern as every other integration in this project (Gemini, Groq,
Tavily, WhatsApp).

No mock mode: sending requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS in
.env, and raises MissingConfigurationError immediately if either is
missing. Like WhatsApp and email, this is an OPTIONAL channel — the
callers (src/api/main.py's _attempt_notifications, scripts/daily_notify.py)
catch that specific error and report the channel as honestly skipped
rather than failing the whole run.

Telegram's real message limit (4096 characters) is far more generous than
WhatsApp's ~1600, and its HTML parse mode gives real bold/formatting — both
used below for a more readable digest than the WhatsApp text version.
"""
from __future__ import annotations

import logging

import httpx

from src.config import settings
from src.errors import MissingConfigurationError

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"
_MAX_EVENTS_IN_MESSAGE = 5
_TELEGRAM_BODY_CHAR_LIMIT = 4000  # Telegram's real cap is 4096 -- headroom left for the HTML tags themselves


def _escape_html(text: str) -> str:
    """Telegram's HTML parse mode only requires these three characters
    escaped (it is not full HTML) — see the Telegram Bot API docs' "HTML
    style" section. Applied to every real, untrusted piece of text
    (headlines, agent names) dropped into the message so a literal '<' or
    '&' in a real headline can never break the message's formatting."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _relevance_flag(event: dict) -> str:
    rel = (event.get("relevance_to_real_estate") or "").lower()
    return "🔴" if rel == "high" else ("🟠" if rel == "medium" else "")


def build_telegram_text(run: dict) -> str:
    """Pure, fully-testable function: turns one run dict (the same shape
    src/api/main.py serializes) into the Telegram message text (HTML parse
    mode). No network, no side effects — exercised directly in
    tests/test_telegram_notifier.py without needing any real credentials.

    Shows each top event's priority_rank (2026-09-21 addition, see
    src/orchestrator/graph.py) the same way the Digest Console does, so
    the "#1" in this message and the "#1" badge on the console agree."""
    report = run.get("report") or {}
    run_date = report.get("report_date") or run.get("run_date", "")
    lines = [f"<b>Orchid Island — Daily Digest ({_escape_html(run_date)})</b>"]

    if not report:
        failed = [s.get("agent") for s in run.get("trace", []) if s.get("status") == "failed"]
        lines.append("This run did not produce a report.")
        if failed:
            lines.append(f"Failed step(s): {_escape_html(', '.join(failed))}.")
        return "\n".join(lines)

    lines.append(_escape_html(report.get("headline", "")))

    if report.get("no_significant_events"):
        lines.append("\nNo significant events today.")
        return "\n".join(lines)

    events = report.get("top_events") or run.get("events") or []
    if events:
        lines.append("\n<b>Top events:</b>")
        for e in events[:_MAX_EVENTS_IN_MESSAGE]:
            flag = _relevance_flag(e)
            rank = e.get("priority_rank")
            rank_label = f"#{rank} " if rank else ""
            headline = _escape_html(e.get("headline", ""))
            lines.append(f"{flag} {rank_label}{headline}".strip())
        if len(events) > _MAX_EVENTS_IN_MESSAGE:
            lines.append(f"…and {len(events) - _MAX_EVENTS_IN_MESSAGE} more in the full report.")

    debate = report.get("debate_highlights") or []
    contested = [d for d in debate if d.upper().startswith("[CONTESTED") or d.upper().startswith("[UNCERTAIN")]
    if contested:
        lines.append(f"\n⚠ {len(contested)} event(s) contested/uncertain in debate — see full report.")

    lines.append("\nFull report + PDF: sent by email.")
    text = "\n".join(lines)
    if len(text) > _TELEGRAM_BODY_CHAR_LIMIT:
        text = text[: _TELEGRAM_BODY_CHAR_LIMIT - 1] + "…"
    return text


def _send_one(chat_id: str, text: str, bot_token: str) -> None:
    resp = httpx.post(
        f"{TELEGRAM_API_BASE}{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=settings.request_timeout_seconds,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        # Telegram can answer HTTP 200 with {"ok": false, "description": ...}
        # for a real failure (chat not found, bot was blocked by that
        # user, etc.) -- raise_for_status() alone would miss this, since
        # it only looks at the HTTP status, not Telegram's own payload.
        raise RuntimeError(data.get("description") or "Telegram API returned ok=false")


def send_telegram_report(run: dict) -> dict:
    """Sends the Telegram digest to every chat id in TELEGRAM_CHAT_IDS.
    Raises MissingConfigurationError if the bot token or chat id list
    isn't set — the caller decides whether that's a hard failure or an
    honest skip (see module docstring). A per-recipient send failure (a
    chat id that never started a conversation with the bot, so Telegram
    won't let it message first — see README for the one-time "/start"
    step each recipient needs) is NOT raised — collected in `failed` so
    one bad chat id doesn't stop the others, the same fail-gracefully
    principle whatsapp_notifier.py already applies."""
    bot_token = settings.require("telegram_bot_token", "TELEGRAM_BOT_TOKEN")
    raw_chat_ids = settings.require("telegram_chat_ids", "TELEGRAM_CHAT_IDS")
    chat_ids = [c.strip() for c in raw_chat_ids.split(",") if c.strip()]

    text = build_telegram_text(run)
    sent_to: list[str] = []
    failed: list[dict] = []
    for chat_id in chat_ids:
        try:
            _send_one(chat_id, text, bot_token)
            sent_to.append(chat_id)
        except MissingConfigurationError:
            raise  # a real config problem, not a per-recipient issue -- let it propagate
        except Exception as exc:
            logger.error("Telegram send failed for %s: %s", chat_id, exc)
            failed.append({"to": chat_id, "error": str(exc)})

    return {"sent_to": sent_to, "failed": failed, "message_body": text}
