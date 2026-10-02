"""Tests for src/services/run_persistence.py -- the persistence logic shared
by POST /run-digest (src/api/main.py) and the standalone
scripts/daily_notify.py (2026-09-11 factor-out, see that module's
docstring). Uses small fake pydantic-shaped objects (a real
OrchestratorState/Event/DailyReport is heavier to construct here) that
expose the same .model_dump(mode="json") / .to_markdown() surface
run_persistence.py actually calls -- everything asserted below is a real
field written by real code, not a stub standing in for the assertion
itself.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services import run_persistence, run_store


class _FakeStep:
    def __init__(self, agent, status, error=None, duration_ms=100):
        self.agent = agent
        self.status = status
        self.error = error
        self.duration_ms = duration_ms

    def model_dump(self, mode="json"):
        return {"agent": self.agent, "status": self.status, "error": self.error, "duration_ms": self.duration_ms}


class _FakeEvent:
    def __init__(self, event_id, headline):
        self.event_id = event_id
        self.headline = headline

    def model_dump(self, mode="json"):
        return {"id": self.event_id, "headline": self.headline}


class _FakeDebateLog:
    def __init__(self, round_count=2):
        self.round_count = round_count

    def model_dump(self, mode="json"):
        return {"round_count": self.round_count, "events": []}


class _FakeReport:
    def __init__(self, headline, no_significant_events=False):
        self.headline = headline
        self.no_significant_events = no_significant_events

    def model_dump(self, mode="json"):
        return {"headline": self.headline, "no_significant_events": self.no_significant_events}

    def to_markdown(self):
        return f"# {self.headline}\n"


class _FakeState:
    def __init__(self, run_date="2026-09-11", trace=None, events=None, debate_log=None, report=None):
        self.run_date = run_date
        self.trace = trace or []
        self.events = events or []
        self.debate_log = debate_log
        self.report = report


def _full_state():
    return _FakeState(
        trace=[_FakeStep("Global Political News Agent", "completed"), _FakeStep("Debate Stage", "completed")],
        events=[_FakeEvent("e1", "Headline one"), _FakeEvent("e2", "Headline two")],
        debate_log=_FakeDebateLog(round_count=2),
        report=_FakeReport("2 events collected across 1 source.", no_significant_events=False),
    )


def test_new_run_id_has_the_expected_shape_and_is_unique():
    a = run_persistence.new_run_id()
    b = run_persistence.new_run_id()
    assert re.match(r"^\d{8}T\d{6}Z-[0-9a-f]{6}$", a)
    assert a != b


def test_serialize_run_maps_every_real_field():
    run = run_persistence.serialize_run("run-123", _full_state())
    assert run["run_id"] == "run-123"
    assert run["run_date"] == "2026-09-11"
    assert run["generated_at"]
    assert run["trace"] == [
        {"agent": "Global Political News Agent", "status": "completed", "error": None, "duration_ms": 100},
        {"agent": "Debate Stage", "status": "completed", "error": None, "duration_ms": 100},
    ]
    assert run["events"] == [{"id": "e1", "headline": "Headline one"}, {"id": "e2", "headline": "Headline two"}]
    assert run["debate_log"] == {"round_count": 2, "events": []}
    assert run["report"] == {"headline": "2 events collected across 1 source.", "no_significant_events": False}
    assert run["report_markdown"] == "# 2 events collected across 1 source.\n"


def test_serialize_run_handles_no_debate_log_or_report():
    state = _FakeState(trace=[_FakeStep("Debate Stage", "failed", error="MissingConfigurationError: ...")])
    run = run_persistence.serialize_run("run-456", state)
    assert run["debate_log"] is None
    assert run["report"] is None
    assert run["report_markdown"] is None
    assert run["events"] == []
    assert run["trace"][0]["status"] == "failed"
    assert "MissingConfigurationError" in run["trace"][0]["error"]


def test_summarize_run_extracts_listing_metadata():
    run = run_persistence.serialize_run("run-789", _full_state())
    summary = run_persistence.summarize_run(run)
    assert summary["run_id"] == "run-789"
    assert summary["run_date"] == "2026-09-11"
    assert summary["headline"] == "2 events collected across 1 source."
    assert summary["event_count"] == 2
    assert summary["no_significant_events"] is False
    assert summary["failed_steps"] == []


def test_summarize_run_reports_failed_steps_and_missing_report():
    state = _FakeState(trace=[_FakeStep("Real Estate Sector Agent", "failed", error="boom")])
    run = run_persistence.serialize_run("run-000", state)
    summary = run_persistence.summarize_run(run)
    assert summary["headline"] is None
    assert summary["event_count"] == 0
    assert summary["no_significant_events"] is False
    assert summary["failed_steps"] == ["Real Estate Sector Agent"]


def test_persist_run_writes_a_real_json_file_and_indexes_it(tmp_path):
    run_id, run, json_path = run_persistence.persist_run(_full_state(), runs_dir=tmp_path)

    assert json_path == tmp_path / f"{run_id}.json"
    assert json_path.exists()
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["run_id"] == run_id
    assert on_disk == run

    db_path = tmp_path / "index.db"
    assert db_path.exists()
    listed = run_store.list_runs(db_path, limit=10)
    assert len(listed) == 1
    assert listed[0]["run_id"] == run_id
    assert listed[0]["headline"] == run["report"]["headline"]


def test_persist_run_called_twice_produces_two_distinct_indexed_runs(tmp_path):
    run_id_1, _run1, _p1 = run_persistence.persist_run(_full_state(), runs_dir=tmp_path)
    run_id_2, _run2, _p2 = run_persistence.persist_run(_full_state(), runs_dir=tmp_path)

    assert run_id_1 != run_id_2
    assert len(list(tmp_path.glob("*.json"))) == 2

    listed = run_store.list_runs(tmp_path / "index.db", limit=10)
    assert {r["run_id"] for r in listed} == {run_id_1, run_id_2}


def test_save_event_note_writes_a_real_note_onto_the_run_json_file(tmp_path):
    """A note is a place for Orchid Island to ask a question or flag
    something about one event -- confirm it actually persists to disk
    (survives a fresh read of the file, not just an in-memory return
    value) keyed by event_id, separate from "report"."""
    run_id, _run, json_path = run_persistence.persist_run(_full_state(), runs_dir=tmp_path)

    note = run_persistence.save_event_note(run_id, "e1", "Is this the same developer as last year?", runs_dir=tmp_path)
    assert note["text"] == "Is this the same developer as last year?"
    assert note["updated_at"]

    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["notes"]["e1"] == note
    assert "e2" not in on_disk["notes"]  # only the event actually noted gets an entry


def test_save_event_note_overwrites_a_previous_note_on_the_same_event(tmp_path):
    run_id, _run, json_path = run_persistence.persist_run(_full_state(), runs_dir=tmp_path)

    run_persistence.save_event_note(run_id, "e1", "First question.", runs_dir=tmp_path)
    run_persistence.save_event_note(run_id, "e1", "Updated question, ignore the first one.", runs_dir=tmp_path)

    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["notes"]["e1"]["text"] == "Updated question, ignore the first one."


def test_save_event_note_with_blank_text_clears_an_existing_note(tmp_path):
    run_id, _run, json_path = run_persistence.persist_run(_full_state(), runs_dir=tmp_path)
    run_persistence.save_event_note(run_id, "e1", "A question worth flagging.", runs_dir=tmp_path)

    result = run_persistence.save_event_note(run_id, "e1", "   ", runs_dir=tmp_path)
    assert result is None

    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert "e1" not in on_disk.get("notes", {})


def test_save_event_note_raises_for_an_unknown_run(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_persistence.save_event_note("does-not-exist", "e1", "text", runs_dir=tmp_path)


def test_save_event_note_raises_for_an_event_not_in_that_run(tmp_path):
    run_id, _run, _json_path = run_persistence.persist_run(_full_state(), runs_dir=tmp_path)
    with pytest.raises(ValueError):
        run_persistence.save_event_note(run_id, "not-a-real-event-id", "text", runs_dir=tmp_path)
