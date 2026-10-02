"""Runnable daily job (2026-09-11 addition): runs the real pipeline once,
persists it exactly like POST /run-digest does, then makes a best-effort
attempt to notify Orchid Island over WhatsApp and email.

This script does NOT loop, sleep, or schedule itself — it runs once and
exits. Trigger it once a day with an OS-level scheduler (Windows Task
Scheduler, since this project runs on a Windows machine) — see
README.md "Daily automatic notifications" for the exact command to
register it.

Notifications are best-effort and independent of each other: if WhatsApp
or email credentials aren't configured in .env, that channel prints a
clear "Skipped" line with the real reason and the script still exits 0 —
the pipeline run and the persisted report already succeeded regardless of
whether anyone was notified about them. See src/services/whatsapp_notifier.py
and src/services/email_notifier.py for what each channel needs.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings
from src.errors import MissingConfigurationError
from src.orchestrator import run_pipeline
from src.services import email_notifier, pdf_export, run_persistence, telegram_notifier, whatsapp_notifier


def _configured(*fields: str) -> bool:
    return all(getattr(settings, f, "") for f in fields)


def main() -> int:
    print("=" * 70)
    print("Orchid Island — Daily Digest + Notify")
    print("=" * 70)
    print("\nConfiguration check:")
    checks = [
        ("LLM_API_KEY (pipeline)", bool(settings.llm_api_key)),
        ("GROQ_API_KEY (pipeline)", bool(settings.groq_api_key)),
        ("WEB_SEARCH_API_KEY (pipeline)", bool(settings.web_search_api_key)),
        ("WhatsApp (Twilio)", _configured("twilio_account_sid", "twilio_auth_token", "twilio_whatsapp_from", "whatsapp_to_numbers")),
        ("Telegram", _configured("telegram_bot_token", "telegram_chat_ids")),
        ("Email (SMTP)", _configured("smtp_host", "smtp_username", "smtp_password", "email_from", "email_to")),
    ]
    for label, ok in checks:
        print(f"  [{'OK ' if ok else '-- '}] {label}")

    print("\nRunning the real pipeline (real search, real LLM calls — this can take a minute or more)...")
    state = run_pipeline()
    run_id, run, json_path = run_persistence.persist_run(state)
    report = run.get("report") or {}
    print(f"\nSaved: {json_path}")
    print(f"Headline: {report.get('headline', '(no report — see trace below)')}")
    failed = [s["agent"] for s in run.get("trace", []) if s.get("status") == "failed"]
    if failed:
        print(f"Failed step(s): {', '.join(failed)}")

    print("\nWhatsApp:")
    try:
        result = whatsapp_notifier.send_whatsapp_report(run)
        print(f"  Sent to: {result['sent_to'] or '(none)'}")
        if result.get("failed"):
            print(f"  Failed for: {result['failed']}")
    except MissingConfigurationError as exc:
        print(f"  Skipped — {exc}")
    except Exception as exc:
        print(f"  Failed — {exc}")

    print("\nTelegram:")
    try:
        result = telegram_notifier.send_telegram_report(run)
        print(f"  Sent to: {result['sent_to'] or '(none)'}")
        if result.get("failed"):
            print(f"  Failed for: {result['failed']}")
    except MissingConfigurationError as exc:
        print(f"  Skipped — {exc}")
    except Exception as exc:
        print(f"  Failed — {exc}")

    print("\nEmail:")
    try:
        pdf_bytes = pdf_export.build_report_pdf(run)
        result = email_notifier.send_email_report(run, pdf_bytes)
        print(f"  Sent to: {result['sent_to']}")
    except MissingConfigurationError as exc:
        print(f"  Skipped — {exc}")
    except Exception as exc:
        print(f"  Failed — {exc}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
