"""Tests for src/services/document_store.py (2026-09-21 addition) --
mirrors the style of run_persistence.py's own tests: real file I/O against
a tmp_path, not mocked, since the whole point is that the JSON/PDF really
land on disk and read back correctly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.event import Event
from src.services import document_store


def _event(headline="Test event") -> Event:
    return Event(
        id="ev-1",
        agent="Uploaded Document Agent",
        headline=headline,
        summary="Summary.",
        confidence=0.7,
        source_url="https://example.test/documents/abc/pdf",
        retrieval_id="retr-1",
    )


def test_save_and_get_document_round_trips_real_events(tmp_path):
    record = document_store.save_document(
        "doc-1",
        filename="report.pdf",
        file_bytes=b"%PDF-1.4 fake pdf bytes",
        events=[_event()],
        page_count=3,
        limitations=["one limitation"],
        documents_dir=tmp_path,
    )
    assert record["event_count"] == 1
    assert record["events"][0]["headline"] == "Test event"

    fetched = document_store.get_document("doc-1", documents_dir=tmp_path)
    assert fetched is not None
    assert fetched["filename"] == "report.pdf"
    assert fetched["page_count"] == 3
    assert fetched["limitations"] == ["one limitation"]
    assert fetched["error"] is None

    pdf_path = document_store.get_document_pdf_path("doc-1", documents_dir=tmp_path)
    assert pdf_path is not None
    assert pdf_path.read_bytes() == b"%PDF-1.4 fake pdf bytes"


def test_save_document_accepts_plain_dicts_too(tmp_path):
    """document_agent.py always builds real Event objects, but
    save_document must not assume that -- a plain dict list (e.g. a future
    caller, or a test) round-trips the same way."""
    record = document_store.save_document(
        "doc-2", filename="x.pdf", file_bytes=b"bytes", events=[{"headline": "already a dict"}],
        page_count=1, limitations=[], documents_dir=tmp_path,
    )
    assert record["events"] == [{"headline": "already a dict"}]


def test_save_document_with_an_error_is_still_saved_and_listed(tmp_path):
    """A failed extraction (e.g. PdfTextNotFoundError) must still show up
    in the console with its real reason, not disappear silently."""
    document_store.save_document(
        "doc-err", filename="scan.pdf", file_bytes=b"bytes", events=[], page_count=0,
        limitations=[], error="No usable text could be found.", documents_dir=tmp_path,
    )
    listed = document_store.list_documents(documents_dir=tmp_path)
    assert len(listed) == 1
    assert listed[0]["error"] == "No usable text could be found."
    assert listed[0]["event_count"] == 0


def test_list_documents_is_newest_first(tmp_path):
    document_store.save_document(
        "doc-a", filename="a.pdf", file_bytes=b"a", events=[], page_count=1,
        limitations=[], documents_dir=tmp_path,
    )
    document_store.save_document(
        "doc-b", filename="b.pdf", file_bytes=b"b", events=[], page_count=1,
        limitations=[], documents_dir=tmp_path,
    )
    listed = document_store.list_documents(documents_dir=tmp_path)
    assert [d["document_id"] for d in listed] == ["doc-b", "doc-a"]


def test_list_documents_on_a_directory_that_does_not_exist_yet_is_an_empty_list_not_a_crash(tmp_path):
    empty_dir = tmp_path / "does_not_exist_yet"
    assert document_store.list_documents(documents_dir=empty_dir) == []


def test_get_document_returns_none_for_an_unknown_id(tmp_path):
    assert document_store.get_document("nope", documents_dir=tmp_path) is None


def test_delete_document_removes_both_files_and_reports_found(tmp_path):
    document_store.save_document(
        "doc-del", filename="d.pdf", file_bytes=b"d", events=[], page_count=1,
        limitations=[], documents_dir=tmp_path,
    )
    assert document_store.delete_document("doc-del", documents_dir=tmp_path) is True
    assert document_store.get_document("doc-del", documents_dir=tmp_path) is None
    assert document_store.get_document_pdf_path("doc-del", documents_dir=tmp_path) is None


def test_delete_document_on_an_already_gone_id_returns_false_not_an_error(tmp_path):
    assert document_store.delete_document("never-existed", documents_dir=tmp_path) is False


def test_new_document_id_is_unique():
    ids = {document_store.new_document_id() for _ in range(20)}
    assert len(ids) == 20
