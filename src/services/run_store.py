"""Lightweight embedded database for run history (SQLite, stdlib only).

Added 2026-09-11 after Orchid Island asked whether this system needs a
database. Before this, it didn't have one: every run was (and still is)
written in full to a human-readable JSON file under reports/runs/ (see
src/api/main.py's run_digest()) -- that JSON file remains the full,
authoritative record of a run. Nothing here replaces it.

What this module adds is a real, queryable index over that history (sort
by date, filter by whether a run had significant events or a failed step)
without re-parsing every JSON file on every GET /runs call -- exactly the
piece of infrastructure flagged as the natural next step once flat files
stop being enough once run history grows. It is deliberately NOT a
general-purpose database: one table, no ORM, no migrations framework,
stdlib `sqlite3` only (already ships with Python -- zero new dependency).

This is also NOT the RAG vector store -- that is separate, still-not-built
infrastructure (Phase 4; see knowledge_base/README.md).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    run_date TEXT NOT NULL,
    headline TEXT,
    event_count INTEGER NOT NULL DEFAULT 0,
    no_significant_events INTEGER NOT NULL DEFAULT 0,
    failed_steps TEXT NOT NULL DEFAULT '[]',
    json_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_generated_at ON runs (generated_at DESC);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    """Opens the index database with pragmas chosen for one specific real
    constraint, found by testing this against Orchid Island's actual
    connected project folder rather than assumed: SQLite's default
    rollback-journal mode failed there with "disk I/O error" on CREATE
    TABLE. That folder is reached through a virtualized/synced mount
    (this project's own folder bridge, and plausibly Windows' OneDrive
    Desktop backup too) -- both are the kind of filesystem where SQLite's
    normal file-based journal + byte-range locking is known to be
    unreliable. journal_mode=MEMORY keeps the rollback journal in RAM
    instead of a second file on disk, and synchronous=OFF skips the fsync
    calls that assume a plain local disk; both were verified to fix the
    real error. This is a safe trade-off specifically because this
    database is a derived, rebuildable INDEX (see backfill_from_json_files
    below) over the JSON files that remain the actual source of truth --
    losing an in-flight index write to a crash costs nothing a re-index
    can't recover, which would not be true if this were the only copy of
    the data."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=MEMORY;")
    conn.execute("PRAGMA synchronous=OFF;")
    conn.executescript(_SCHEMA)
    return conn


def record_run(db_path: Path, summary: dict, json_path: Path) -> None:
    """Upsert one run's summary row. Called right after main.py writes the
    full JSON file for that run -- the JSON file stays the full record;
    this row is only an index over it, keyed by the same run_id."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO runs (run_id, generated_at, run_date, headline, event_count,
                                  no_significant_events, failed_steps, json_path)
               VALUES (:run_id, :generated_at, :run_date, :headline, :event_count,
                       :no_significant_events, :failed_steps, :json_path)
               ON CONFLICT(run_id) DO UPDATE SET
                   generated_at=excluded.generated_at, run_date=excluded.run_date,
                   headline=excluded.headline, event_count=excluded.event_count,
                   no_significant_events=excluded.no_significant_events,
                   failed_steps=excluded.failed_steps, json_path=excluded.json_path""",
            {
                "run_id": summary["run_id"],
                "generated_at": summary["generated_at"],
                "run_date": summary["run_date"],
                "headline": summary.get("headline"),
                "event_count": summary.get("event_count", 0),
                "no_significant_events": int(bool(summary.get("no_significant_events"))),
                "failed_steps": json.dumps(summary.get("failed_steps", [])),
                "json_path": str(json_path),
            },
        )
        conn.commit()
    finally:
        conn.close()


def list_runs(db_path: Path, limit: int = 20) -> list[dict]:
    """Real, indexed history -- every row here was written by a real
    record_run() call after a real /run-digest; an empty list just means no
    run (or no backfill source) exists yet, same guarantee the old
    directory-scan implementation gave."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT run_id, generated_at, run_date, headline, event_count, "
            "no_significant_events, failed_steps, json_path FROM runs "
            "ORDER BY generated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "run_id": r[0],
            "generated_at": r[1],
            "run_date": r[2],
            "headline": r[3],
            "event_count": r[4],
            "no_significant_events": bool(r[5]),
            "failed_steps": json.loads(r[6]),
        }
        for r in rows
    ]


def get_json_path(db_path: Path, run_id: str) -> Optional[Path]:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT json_path FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    finally:
        conn.close()
    return Path(row[0]) if row else None


def backfill_from_json_files(runs_dir: Path, db_path: Path) -> int:
    """One-time recovery: if the index is empty but reports/runs/*.json
    files already exist (from before this feature existed -- e.g. the real
    2026-09-10 run shipped with this project), index them so real history
    isn't silently dropped just because the database is new. No-ops (and
    is cheap to call) once the index already has rows. Returns how many
    rows were inserted this call."""
    conn = _connect(db_path)
    try:
        existing = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        if existing > 0:
            return 0
    finally:
        conn.close()

    count = 0
    for f in sorted(runs_dir.glob("*.json")):
        try:
            run = json.loads(f.read_text(encoding="utf-8"))
            report = run.get("report") or {}
            record_run(
                db_path,
                {
                    "run_id": run["run_id"],
                    "generated_at": run["generated_at"],
                    "run_date": run["run_date"],
                    "headline": report.get("headline"),
                    "event_count": len(run.get("events") or []),
                    "no_significant_events": report.get("no_significant_events", False),
                    "failed_steps": [s["agent"] for s in run.get("trace", []) if s.get("status") == "failed"],
                },
                f,
            )
            count += 1
        except (json.JSONDecodeError, KeyError):
            continue
    return count
