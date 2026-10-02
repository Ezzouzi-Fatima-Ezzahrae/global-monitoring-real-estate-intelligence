#!/usr/bin/env python3
"""Runnable demo: `python scripts/demo_run.py`.

Runs the full V1+Phase3 pipeline (5 monitoring agents -> debate -> digest
report) and prints the result.

There is no mock mode: this always makes real calls. LLM_API_KEY,
GROQ_API_KEY, and WEB_SEARCH_API_KEY must all be set in .env (see
.env.example) — this script checks upfront and tells you exactly which
ones are missing rather than letting the pipeline fail confusingly partway
through, or silently substituting fake data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings
from src.orchestrator import run_pipeline

REQUIRED_CREDENTIALS = [
    ("llm_api_key", "LLM_API_KEY", "primary LLM — used by all 5 monitoring agents and as the debate 'defender'"),
    ("groq_api_key", "GROQ_API_KEY", "debate 'challenger' voice (Phase 3 adversarial review)"),
    ("web_search_api_key", "WEB_SEARCH_API_KEY", "web search — required for monitoring agents to retrieve anything real"),
]


def check_configuration() -> bool:
    """Print what's configured and what's missing. Returns True only if
    everything required is present. This is the code-level equivalent of
    "asking" for what's needed, up front, before running anything."""
    print("Configuration check:")
    all_present = True
    for field_name, env_var, purpose in REQUIRED_CREDENTIALS:
        present = bool(getattr(settings, field_name))
        print(f"  [{'OK ' if present else 'MISSING'}] {env_var}  ({purpose})")
        all_present = all_present and present
    print()
    if not all_present:
        print(
            "One or more required credentials are missing. This system has no "
            "mock/fallback mode, so it cannot produce a real result without them.\n"
            "Set the missing variable(s) above in .env (see .env.example) and re-run."
        )
    return all_present


def main() -> None:
    if not check_configuration():
        sys.exit(1)

    print("Running pipeline...\n")
    state = run_pipeline()

    print("Agent trace:")
    for step in state.trace:
        status = step.status.upper()
        line = f"  [{status:9s}] {step.agent} ({step.duration_ms} ms)"
        if step.error:
            line += f" — {step.error}"
        print(line)
    print()
    print(state.report.to_markdown() if state.report else "No report produced.")


if __name__ == "__main__":
    main()
