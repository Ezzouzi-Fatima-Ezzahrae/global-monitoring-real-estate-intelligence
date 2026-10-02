"""Tests for the POST/GET/DELETE /documents* routes added to
src/api/main.py (2026-09-21). Uses FastAPI's real TestClient (real request/
response cycle, real multipart upload parsing) with only the LLM call
stubbed -- no real Gemini/Groq call, no real network."""
import io
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

import src.api.main as api_main


def _real_pdf_bytes(*lines: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 750
    for line in lines:
        c.drawString(100, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def _blank_pdf_bytes() -> bytes:
    buf = io.BytesIO()
    canvas.Canvas(buf).save()
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "DOCUMENTS_DIR", tmp_path)
    return TestClient(api_main.app)


_FAKE_EXTRACTION = {
    "events": [
        {
            "headline": "New tourism incentive program",
            "summary": "A government program targeting Marrakech hospitality investment.",
            "sentiment": "positive",
            "relevance_to_real_estate": "high",
            "confidence": 0.8,
            "agent_interpretation": "Likely to boost luxury demand.",
            "supporting_quote": "tourism investment incentive program",
        }
    ]
}


def test_upload_a_real_pdf_returns_real_extracted_events(client, fake_credentials):
    pdf_bytes = _real_pdf_bytes(
        "Marrakech tourism investment report",
        "A new tourism investment incentive program was announced in March 2026.",
    )
    with patch("src.services.llm_client.llm_client.complete_json", return_value=_FAKE_EXTRACTION):
        resp = client.post("/documents/upload", files={"file": ("report.pdf", pdf_bytes, "application/pdf")})

    assert resp.status_code == 200
    body = resp.json()
    assert body["event_count"] == 1
    assert body["events"][0]["headline"] == "New tourism incentive program"
    # source_url must be this same document's real, resolvable pdf URL
    assert body["events"][0]["source_url"].endswith(f"/documents/{body['document_id']}/pdf")


def test_uploaded_document_shows_up_in_list_and_get(client, fake_credentials):
    pdf_bytes = _real_pdf_bytes("A document about Marrakech real estate developments and tourism.")
    with patch("src.services.llm_client.llm_client.complete_json", return_value={"events": []}):
        upload_resp = client.post("/documents/upload", files={"file": ("x.pdf", pdf_bytes, "application/pdf")})
    doc_id = upload_resp.json()["document_id"]

    list_resp = client.get("/documents")
    assert list_resp.status_code == 200
    assert any(d["document_id"] == doc_id for d in list_resp.json())

    get_resp = client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["filename"] == "x.pdf"


def test_get_document_pdf_serves_back_the_real_original_file(client, fake_credentials):
    pdf_bytes = _real_pdf_bytes("Original content that must be served back byte for byte, real estate news.")
    with patch("src.services.llm_client.llm_client.complete_json", return_value={"events": []}):
        upload_resp = client.post("/documents/upload", files={"file": ("orig.pdf", pdf_bytes, "application/pdf")})
    doc_id = upload_resp.json()["document_id"]

    pdf_resp = client.get(f"/documents/{doc_id}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content == pdf_bytes


def test_delete_document_removes_it(client, fake_credentials):
    pdf_bytes = _real_pdf_bytes("A document to be deleted, about real estate in Morocco.")
    with patch("src.services.llm_client.llm_client.complete_json", return_value={"events": []}):
        upload_resp = client.post("/documents/upload", files={"file": ("del.pdf", pdf_bytes, "application/pdf")})
    doc_id = upload_resp.json()["document_id"]

    delete_resp = client.delete(f"/documents/{doc_id}")
    assert delete_resp.status_code == 200
    assert client.get(f"/documents/{doc_id}").status_code == 404
    assert client.get(f"/documents/{doc_id}/pdf").status_code == 404


def test_get_and_delete_unknown_document_id_is_a_real_404(client):
    assert client.get("/documents/does-not-exist").status_code == 404
    assert client.delete("/documents/does-not-exist").status_code == 404


def test_upload_rejects_non_pdf_file(client):
    resp = client.post("/documents/upload", files={"file": ("notes.txt", b"hello world", "text/plain")})
    assert resp.status_code == 400


def test_upload_rejects_empty_file(client):
    resp = client.post("/documents/upload", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert resp.status_code == 400


def test_upload_rejects_file_over_the_configured_size_limit(client, monkeypatch):
    """2026-09-25 fix: the old hardcoded 25 MB cap rejected a real ~94 MB
    upload outright. The limit is now src.config.settings.document_upload_max_bytes
    (default 200 MB, raisable via .env) -- this test drives it down to a
    tiny value so a real PDF reliably exceeds it without generating a huge
    file in the test suite, and checks the message is in human MB, not raw
    byte counts."""
    from src.config import settings

    monkeypatch.setattr(settings, "document_upload_max_bytes", 100)
    pdf_bytes = _real_pdf_bytes("A real PDF that is bigger than a tiny configured limit, about real estate.")
    resp = client.post("/documents/upload", files={"file": ("big.pdf", pdf_bytes, "application/pdf")})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "too large" in detail.lower()
    assert "MB" in detail


def test_upload_accepts_a_file_just_under_the_configured_size_limit(client, monkeypatch, fake_credentials):
    """Same real file as above, but with the limit set just above its real
    size -- confirms the boundary is a real, working check (not always-fail
    or always-pass), and that a file within the limit is genuinely
    processed rather than rejected."""
    from src.config import settings

    pdf_bytes = _real_pdf_bytes("A real PDF just under the configured size limit, about real estate in Morocco.")
    monkeypatch.setattr(settings, "document_upload_max_bytes", len(pdf_bytes) + 10)
    with patch("src.services.llm_client.llm_client.complete_json", return_value={"events": []}):
        resp = client.post("/documents/upload", files={"file": ("ok.pdf", pdf_bytes, "application/pdf")})
    assert resp.status_code == 200


def test_upload_a_pdf_with_no_extractable_text_is_a_real_422_and_is_still_saved(client, fake_credentials):
    resp = client.post("/documents/upload", files={"file": ("scan.pdf", _blank_pdf_bytes(), "application/pdf")})
    assert resp.status_code == 422
    assert "no usable text" in resp.json()["detail"].lower() or "scanned" in resp.json()["detail"].lower()

    listed = client.get("/documents").json()
    assert len(listed) == 1
    assert listed[0]["error"] is not None


def test_upload_a_scan_when_ocr_packages_are_missing_is_a_real_503_not_saved(client, monkeypatch):
    """2026-09-25: OCR being turned on but not actually installed is a
    setup problem (same as a missing LLM_API_KEY above), not something
    wrong with this particular file -- it must not be saved as a
    permanently-failed document tied to this one scan."""
    import src.tools.pdf_extraction as pdf_extraction

    monkeypatch.setattr(pdf_extraction, "pymupdf", None)
    # Needs a real page with no usable text (an OCR candidate) -- unlike
    # _blank_pdf_bytes()'s zero-page PDF, which never reaches the OCR
    # check at all.
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.showPage()
    c.save()
    one_blank_page_pdf = buf.getvalue()

    resp = client.post("/documents/upload", files={"file": ("scan.pdf", one_blank_page_pdf, "application/pdf")})
    assert resp.status_code == 503
    assert "pip install" in resp.json()["detail"].lower()
    assert client.get("/documents").json() == []


def test_upload_without_llm_api_key_is_a_real_503_not_a_silent_failure(client, monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "")
    pdf_bytes = _real_pdf_bytes("A document with real text but no LLM credential configured, about real estate.")
    resp = client.post("/documents/upload", files={"file": ("x.pdf", pdf_bytes, "application/pdf")})
    assert resp.status_code == 503
    assert "LLM_API_KEY" in resp.json()["detail"]


def test_low_relevance_extracted_items_never_reach_the_console(client, fake_credentials):
    pdf_bytes = _real_pdf_bytes("A document with one relevant item and one irrelevant item about Morocco.")
    mixed = {
        "events": [
            {"headline": "Relevant", "summary": "s", "sentiment": "neutral", "relevance_to_real_estate": "high", "confidence": 0.7, "agent_interpretation": ""},
            {"headline": "Irrelevant", "summary": "s", "sentiment": "neutral", "relevance_to_real_estate": "low", "confidence": 0.2, "agent_interpretation": ""},
        ]
    }
    with patch("src.services.llm_client.llm_client.complete_json", return_value=mixed):
        resp = client.post("/documents/upload", files={"file": ("x.pdf", pdf_bytes, "application/pdf")})

    headlines = [e["headline"] for e in resp.json()["events"]]
    assert headlines == ["Relevant"]
