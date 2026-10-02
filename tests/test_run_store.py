"""Tests for src/services/run_store.py — the SQLite index over reports/runs/*.json.

Uses pytest's built-in tmp_path fixture so every test gets its own throwaway
directory/database — never the project's real reports/runs/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services import run_store


def _summary(run_id, **overrides):
    s = {
        "run_id": run_id,
        "generated_at": f"2026-09-{run_id[-2:]}T09:00:00+00:00",
        "run_date": "2026-09-11",
        "headline": "Test headline",
        "event_count": 3,
        "no_significant_events": False,
        "failed_steps": [],
    }
    s.update(overrides)
    return s


def test_list_runs_is_empty_before_any_record(tmp_path):
    db_path = tmp_path / "index.db"
    assert run_store.list_runs(db_path) == []


def test_record_and_list_round_trips_a_real_row(tmp_path):
    db_path = tmp_path / "index.db"
    json_path = tmp_path / "run1.json"
    run_store.record_run(db_path, _summary("run-01"), json_path)

    rows = run_store.list_runs(db_path)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-01"
    assert rows[0]["event_count"] == 3
    assert rows[0]["no_significant_events"] is False


def test_list_runs_orders_newest_first(tmp_path):
    db_path = tmp_path / "index.db"
    run_store.record_run(db_path, _summary("run-01", generated_at="2026-09-01T09:00:00+00:00"), tmp_path / "a.json")
    run_store.record_run(db_path, _summary("run-02", generated_at="2026-09-03T09:00:00+00:00"), tmp_path / "b.json")
    run_store.record_run(db_path, _summary("run-03", generated_at="2026-09-02T09:00:00+00:00"), tmp_path / "c.json")

    rows = run_store.list_runs(db_path)
    assert [r["run_id"] for r in rows] == ["run-02", "run-03", "run-01"]


def test_record_run_upserts_rather_than_duplicating(tmp_path):
    db_path = tmp_path / "index.db"
    run_store.record_run(db_path, _summary("run-01", headline="First"), tmp_path / "a.json")
    run_store.record_run(db_path, _summary("run-01", headline="Updated"), tmp_path / "a.json")

    rows = run_store.list_runs(db_path)
    assert len(rows) == 1
    assert rows[0]["headline"] == "Updated"


def test_get_json_path_returns_none_for_unknown_run(tmp_path):
    db_path = tmp_path / "index.db"
    assert run_store.get_json_path(db_path, "does-not-exist") is None


def test_backfill_indexes_preexisting_json_files_without_dropping_real_history(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    real_run = {
        "run_id": "20260910T120000Z-real01",
        "generated_at": "2026-09-10T12:00:00+00:00",
        "run_date": "2026-09-10",
        "events": [{"id": "e1"}, {"id": "e2"}],
        "trace": [{"agent": "Real Estate Sector Agent", "status": "completed"}, {"agent": "Debate Stage", "status": "failed"}],
        "report": {"headline": "8 events collected", "no_significant_events": False},
    }
    (runs_dir / f"{real_run['run_id']}.json").write_text(json.dumps(real_run), encoding="utf-8")

    db_path = tmp_path / "index.db"
    inserted = run_store.backfill_from_json_files(runs_dir, db_path)
    assert inserted == 1

    rows = run_store.list_runs(db_path)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "20260910T120000Z-real01"
    assert rows[0]["event_count"] == 2
    assert rows[0]["failed_steps"] == ["Debate Stage"]


def test_backfill_is_a_noop_once_the_index_already_has_rows(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "a.json").write_text(json.dumps({"run_id": "a", "generated_at": "t", "run_date": "d", "events": [], "trace": [], "report": {}}), encoding="utf-8")

    db_path = tmp_path / "index.db"
    run_store.record_run(db_path, _summary("manual-01"), tmp_path / "manual.json")

    inserted = run_store.backfill_from_json_files(runs_dir, db_path)
    assert inserted == 0
    assert len(run_store.list_runs(db_path)) == 1
