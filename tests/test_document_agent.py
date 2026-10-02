"""Tests for src/agents/document_agent.py (2026-09-21 addition). Stubs
llm_client.extract_events_from_document directly (same dependency-
injection style conftest.py's stub_summarize_event uses for the
monitoring agents) -- no real network, no real PDF needed here since
pdf_extraction.py is tested on its own in tests/test_pdf_extraction.py."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.agents.document_agent import DOCUMENT_AGENT_NAME, analyze_uploaded_pdf
from src.models.event import SourceQuality, SourceType
from src.tools.pdf_extraction import ExtractedPdf, PdfTextNotFoundError


def _extracted(text="Real extracted document text about Marrakech real estate.", truncated=False, page_count=2):
    # One real page's worth of text per page_count, matching text -- good
    # enough for tests that don't specifically exercise page/section
    # validation (see test_document_agent_page_reference.py for those).
    return ExtractedPdf(text=text, page_count=page_count, truncated=truncated, page_texts=[text] * page_count)


def test_builds_real_events_from_extracted_items():
    raw = [
        {
            "headline": "New tourism incentive program",
            "summary": "Government incentive targeting Marrakech hospitality.",
            "sentiment": "positive",
            "relevance_to_real_estate": "high",
            "confidence": 0.85,
            "agent_interpretation": "Likely to boost luxury demand.",
            "supporting_quote": "a new tourism investment incentive program",
        }
    ]
    with patch("src.agents.document_agent.extract_pdf_text", return_value=_extracted()), patch(
        "src.services.llm_client.llm_client.extract_events_from_document", return_value=raw
    ):
        result = analyze_uploaded_pdf(b"fake bytes", filename="report.pdf", source_url="http://localhost:8000/documents/abc/pdf", document_id="abc")

    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event.agent == DOCUMENT_AGENT_NAME
    assert event.headline == "New tourism incentive program"
    assert str(event.source_url) == "http://localhost:8000/documents/abc/pdf"
    assert event.source_name == "Uploaded document — report.pdf"
    assert event.published_at is None  # honest: no reliable publish date for an uploaded doc
    assert "a new tourism investment incentive program" in event.agent_interpretation
    assert result["page_count"] == 2
    # 2026-09-24: source traceability defaults -- no "page" key in raw, so
    # neither page nor section is fabricated, and the quality tier reflects
    # that this specific event's page could not be pinned down.
    assert event.source_type == SourceType.PDF
    assert event.source_quality == SourceQuality.EARLY_UNCONFIRMED
    assert event.pdf_reference.document_id == "abc"
    assert event.pdf_reference.page is None
    assert event.pdf_reference.section is None


def test_a_real_in_range_page_is_kept_and_source_quality_upgraded():
    page_texts = ["Page one text, nothing relevant here.", "MARKET OUTLOOK\nA new tourism incentive was announced."]
    extracted = ExtractedPdf(text="\n\n".join(page_texts), page_count=2, truncated=False, page_texts=page_texts)
    raw = [{
        "headline": "New tourism incentive", "summary": "s", "relevance_to_real_estate": "high",
        "confidence": 0.8, "sentiment": "positive", "agent_interpretation": "",
        "page": 2, "section": "MARKET OUTLOOK",
    }]
    with patch("src.agents.document_agent.extract_pdf_text", return_value=extracted), patch(
        "src.services.llm_client.llm_client.extract_events_from_document", return_value=raw
    ):
        result = analyze_uploaded_pdf(b"fake bytes", filename="report.pdf", source_url="http://x/pdf", document_id="doc7")

    event = result["events"][0]
    assert event.pdf_reference.page == 2
    assert event.pdf_reference.section == "MARKET OUTLOOK"
    assert event.source_quality == SourceQuality.CREDIBLE_SECONDARY


def test_an_out_of_range_page_is_dropped_not_shown():
    page_texts = ["Only page."]
    extracted = ExtractedPdf(text=page_texts[0], page_count=1, truncated=False, page_texts=page_texts)
    raw = [{
        "headline": "Some event", "summary": "s", "relevance_to_real_estate": "high",
        "confidence": 0.6, "sentiment": "neutral", "agent_interpretation": "",
        "page": 5, "section": "Made-up heading",  # the model claimed a page that doesn't exist
    }]
    with patch("src.agents.document_agent.extract_pdf_text", return_value=extracted), patch(
        "src.services.llm_client.llm_client.extract_events_from_document", return_value=raw
    ):
        result = analyze_uploaded_pdf(b"fake bytes", filename="report.pdf", source_url="http://x/pdf", document_id="doc8")

    event = result["events"][0]
    assert event.pdf_reference.page is None
    assert event.pdf_reference.section is None
    assert event.source_quality == SourceQuality.EARLY_UNCONFIRMED


def test_a_section_not_actually_on_that_page_is_dropped_not_shown():
    """The model can get the page right but invent (or misplace) a heading
    -- that must not be shown as if it were confirmed."""
    page_texts = ["Page one.", "Page two has no headings, just plain prose about Marrakech tourism."]
    extracted = ExtractedPdf(text="\n\n".join(page_texts), page_count=2, truncated=False, page_texts=page_texts)
    raw = [{
        "headline": "Some event", "summary": "s", "relevance_to_real_estate": "high",
        "confidence": 0.6, "sentiment": "neutral", "agent_interpretation": "",
        "page": 2, "section": "INVESTOR OUTLOOK",  # not real text on page 2
    }]
    with patch("src.agents.document_agent.extract_pdf_text", return_value=extracted), patch(
        "src.services.llm_client.llm_client.extract_events_from_document", return_value=raw
    ):
        result = analyze_uploaded_pdf(b"fake bytes", filename="report.pdf", source_url="http://x/pdf", document_id="doc9")

    event = result["events"][0]
    assert event.pdf_reference.page == 2  # the page itself is real and in range
    assert event.pdf_reference.section is None  # but the invented heading is not kept


def test_skips_items_judged_low_relevance():
    """Same standard as every monitoring agent (2026-09-17, at Orchid
    Island's request): low relevance means genuinely not useful, so it's
    dropped, not just tagged."""
    raw = [
        {"headline": "Relevant", "summary": "s", "relevance_to_real_estate": "high", "confidence": 0.7, "sentiment": "neutral", "agent_interpretation": ""},
        {"headline": "Not relevant", "summary": "s", "relevance_to_real_estate": "low", "confidence": 0.2, "sentiment": "neutral", "agent_interpretation": ""},
    ]
    with patch("src.agents.document_agent.extract_pdf_text", return_value=_extracted()), patch(
        "src.services.llm_client.llm_client.extract_events_from_document", return_value=raw
    ):
        result = analyze_uploaded_pdf(b"fake bytes", filename="x.pdf", source_url="http://x/pdf", document_id="doc1")

    assert len(result["events"]) == 1
    assert result["events"][0].headline == "Relevant"


def test_an_empty_extraction_is_a_valid_honest_result_not_an_error():
    with patch("src.agents.document_agent.extract_pdf_text", return_value=_extracted()), patch(
        "src.services.llm_client.llm_client.extract_events_from_document", return_value=[]
    ):
        result = analyze_uploaded_pdf(b"fake bytes", filename="x.pdf", source_url="http://x/pdf", document_id="doc1")
    assert result["events"] == []
    assert result["limitations"] == []


def test_one_malformed_extracted_item_does_not_lose_the_others():
    raw = [
        {"headline": "Good event", "summary": "s", "relevance_to_real_estate": "high", "confidence": 0.7, "sentiment": "neutral", "agent_interpretation": ""},
        {"summary": "missing headline field entirely"},  # malformed -- Event(...) will raise on this one
    ]
    with patch("src.agents.document_agent.extract_pdf_text", return_value=_extracted()), patch(
        "src.services.llm_client.llm_client.extract_events_from_document", return_value=raw
    ):
        result = analyze_uploaded_pdf(b"fake bytes", filename="x.pdf", source_url="http://x/pdf", document_id="doc1")
    assert len(result["events"]) == 1
    assert result["events"][0].headline == "Good event"


def test_reports_truncation_limitations_honestly():
    with patch("src.agents.document_agent.extract_pdf_text", return_value=_extracted(truncated=True, page_count=80)), patch(
        "src.services.llm_client.llm_client.extract_events_from_document", return_value=[]
    ):
        result = analyze_uploaded_pdf(b"fake bytes", filename="long.pdf", source_url="http://x/pdf", document_id="doc1")
    assert any("80 pages" in lim for lim in result["limitations"])


def test_reports_ocr_usage_and_ocr_page_cap_limitations_honestly():
    """2026-09-25 addition: when pdf_extraction.py had to OCR real scanned
    pages, and/or hit its page cap, that must show up as an honest
    limitation the same way truncation already does."""
    extracted = ExtractedPdf(
        text="Real extracted document text about Marrakech real estate.",
        page_count=5,
        truncated=False,
        page_texts=["Real extracted document text about Marrakech real estate."] * 5,
        ocr_pages_used=2,
        ocr_pages_skipped=3,
    )
    with patch("src.agents.document_agent.extract_pdf_text", return_value=extracted), patch(
        "src.services.llm_client.llm_client.extract_events_from_document", return_value=[]
    ):
        result = analyze_uploaded_pdf(b"fake bytes", filename="scan.pdf", source_url="http://x/pdf", document_id="doc1")
    assert any("2 page(s)" in lim and "OCR" in lim for lim in result["limitations"])
    assert any("3 more scanned page(s)" in lim for lim in result["limitations"])


def test_pdf_text_not_found_error_propagates_uncaught():
    """POST /documents/upload relies on this propagating so it can return
    a real, honest 4xx with the exact reason -- document_agent must not
    swallow it into a fabricated empty success."""
    with patch("src.agents.document_agent.extract_pdf_text", side_effect=PdfTextNotFoundError("no text found")):
        with pytest.raises(PdfTextNotFoundError):
            analyze_uploaded_pdf(b"fake bytes", filename="scan.pdf", source_url="http://x/pdf", document_id="doc1")
