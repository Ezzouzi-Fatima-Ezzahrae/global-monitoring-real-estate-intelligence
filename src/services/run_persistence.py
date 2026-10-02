"""Shared persistence for one pipeline run: writes the full JSON record
under reports/runs/<run_id>.json and indexes it in the SQLite database
(src/services/run_store.py).

Factored out (2026-09-11) so that src/api/main.py's POST /run-digest and
the standalone scripts/daily_notify.py (triggered by an OS-level daily
scheduler, not this API) persist a run identically -- one place, not two
copies of the same logic that could quietly drift apart.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.services import run_store, translation

RUNS_DIR_DEFAULT = Path(__file__).resolve().parents[2] / "reports" / "runs"


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


def serialize_run(run_id: str, state) -> dict:
    """Full, real pipeline output as JSON — every field here traces back to
    a real Event/DebateLog/DailyReport produced by this run, nothing added
    for display purposes. mode="json" makes pydantic's HttpUrl/date/enum
    fields plain JSON-safe values."""
    # 2026-09-21: the Digest Console renders straight from this "events"
    # list (not report.top_events), so it needs to already be in priority
    # order -- _format_report_node assigns priority_rank on each Event
    # object in place (see its own comment on why: PipelineState.events'
    # operator.add reducer would duplicate the list if the node tried to
    # replace it instead), but state.events' own list order is still
    # whatever the monitoring agents happened to finish in. Sort here, once,
    # at the one place both the API and any other consumer of this JSON
    # read from. None (an event Judge never assessed, or the whole run
    # predates this feature) sorts last, never crashes the sort.
    ranked_events = sorted(
        state.events, key=lambda e: e.priority_rank if e.priority_rank is not None else float("inf")
    )
    return {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_date": state.run_date,
        "trace": [s.model_dump(mode="json") for s in state.trace],
        "events": [e.model_dump(mode="json") for e in ranked_events],
        "debate_log": state.debate_log.model_dump(mode="json") if state.debate_log else None,
        "report": state.report.model_dump(mode="json") if state.report else None,
        "report_markdown": state.report.to_markdown() if state.report else None,
    }


def summarize_run(run: dict) -> dict:
    """Lightweight metadata for the /runs list view and the SQLite index —
    avoids shipping/storing every event's full text just to render history."""
    report = run.get("report") or {}
    return {
        "run_id": run["run_id"],
        "generated_at": run["generated_at"],
        "run_date": run["run_date"],
        "headline": report.get("headline"),
        "event_count": len(run.get("events") or []),
        "no_significant_events": report.get("no_significant_events", False),
        "failed_steps": [s["agent"] for s in run.get("trace", []) if s.get("status") == "failed"],
    }


def persist_run(state, runs_dir: Path = RUNS_DIR_DEFAULT) -> tuple[str, dict, Path]:
    """Writes the run's full JSON file and indexes it in SQLite (index.db
    inside runs_dir). Returns (run_id, run_dict, json_path). `runs_dir`
    defaults to the real reports/runs/ folder but is overridable — main.py
    passes its own (possibly test-monkeypatched) RUNS_DIR through here."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = new_run_id()
    run = serialize_run(run_id, state)
    json_path = runs_dir / f"{run_id}.json"
    json_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    run_store.record_run(runs_dir / "index.db", summarize_run(run), json_path)
    return run_id, run, json_path


def save_event_note(run_id: str, event_id: str, text: str, runs_dir: Path = RUNS_DIR_DEFAULT) -> dict | None:
    """Saves (or clears) a user-authored note against one event in an
    already-persisted run — e.g. a question Orchid Island wants to flag
    while reading the Digest Console. Stored as its own top-level "notes"
    map on the run's JSON file (event_id -> {text, updated_at}) rather than
    folded into "report", because a note is never generated or altered by
    the pipeline, only by whoever is reading it — keeping that boundary
    clear matters for a system whose whole point is that nothing shown is
    fabricated.

    Blank/whitespace-only text clears an existing note instead of storing
    an empty one. Returns the saved note dict, or None if it was cleared.
    Raises FileNotFoundError if the run doesn't exist, ValueError if the
    event isn't part of that run — src/api/main.py turns both into a real
    404 rather than silently writing a note against a bad id."""
    json_path = runs_dir / f"{run_id}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"No run found with id {run_id!r}")

    run = json.loads(json_path.read_text(encoding="utf-8"))
    event_ids = {e.get("id") for e in run.get("events") or []}
    if event_id not in event_ids:
        raise ValueError(f"No event {event_id!r} in run {run_id!r}")

    notes = run.setdefault("notes", {})
    clean_text = text.strip()
    if clean_text:
        note = {"text": clean_text, "updated_at": datetime.now(timezone.utc).isoformat()}
        notes[event_id] = note
    else:
        notes.pop(event_id, None)
        note = None

    json_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    return note


def get_or_create_translation(run_id: str, lang: str, runs_dir: Path = RUNS_DIR_DEFAULT) -> dict:
    """Returns this run's cached French/Arabic translation (src/services/
    translation.py), translating and persisting it into the run's own JSON
    file the first time it is asked for -- on demand, not at generation
    time (see that module's docstring for why). A second call for the
    same run+lang is a pure cache read: no LLM call, no cost, no wait.
    Raises FileNotFoundError for an unknown run_id (src/api/main.py turns
    that into a real 404, same as every other /runs/{run_id}* route) and
    lets translate_run's own MissingConfigurationError/ValueError
    propagate honestly on a real failure -- never cached as if it
    succeeded."""
    json_path = runs_dir / f"{run_id}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"No run found with id {run_id!r}")

    run = json.loads(json_path.read_text(encoding="utf-8"))
    translations = run.setdefault("translations", {})
    if lang in translations:
        return translations[lang]

    translated = translation.translate_run(run, lang)
    translations[lang] = translated
    json_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    return translated
