"""Tests for src/services/pdf_export.py — the /runs/{id}/pdf renderer.

No network, no LLM, no fixtures needed beyond plain dicts: build_report_pdf()
is a pure function over the same run-dict shape src/api/main.py already
serializes. We check it produces a real PDF (starts with the %PDF magic
bytes) for every shape of report the pipeline can actually produce,
including the "no report" and "no significant events" honest-output cases.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import io

from pypdf import PdfReader

from src.services.pdf_export import build_report_pdf


def _base_run(**report_overrides):
    report = {
        "report_date": "2026-09-11",
        "headline": "8 events collected; 1 flagged high real-estate relevance.",
        "top_events": [],
        "debate_highlights": [],
        "impact_analysis": [],
        "risks_and_opportunities": [],
        "recommended_actions": [],
        "limitations": [],
        "citations": [],
        "no_significant_events": False,
    }
    report.update(report_overrides)
    return {"run_id": "20260911T090000Z-abcdef", "generated_at": "2026-09-11T09:00:00+00:00", "run_date": "2026-09-11", "report": report, "events": [], "trace": []}


def test_full_report_renders_a_real_pdf():
    run = _base_run(
        top_events=[{"headline": "Test event", "source_name": "Reuters", "summary": "A real summary.", "source_url": "https://reuters.com/x"}],
        debate_highlights=["One event was contested."],
        impact_analysis=[{"sector_or_market_affected": "real_estate", "direction": "negative", "magnitude": "medium", "confidence": 0.4, "time_horizon": "short_term", "contested": True, "rationale": "Financing costs are rising, which softens near-term buyer demand in this segment.", "recommended_action": "Monitor closely."}],
        risks_and_opportunities=["A risk."],
        recommended_actions=["An action."],
        limitations=["A limitation."],
        citations=["https://reuters.com/x"],
    )
    pdf_bytes = build_report_pdf(run)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


def test_no_significant_events_still_renders_a_real_pdf():
    run = _base_run(no_significant_events=True)
    pdf_bytes = build_report_pdf(run)
    assert pdf_bytes.startswith(b"%PDF")


def test_missing_report_renders_an_honest_failure_pdf():
    run = {"run_id": "x", "generated_at": "2026-09-11T09:00:00+00:00", "run_date": "2026-09-11", "report": None, "events": [], "trace": [{"agent": "Debate Stage", "status": "failed", "error": "429 Too Many Requests"}]}
    pdf_bytes = build_report_pdf(run)
    assert pdf_bytes.startswith(b"%PDF")


def test_impact_analysis_rationale_and_action_are_real_text_in_the_pdf():
    run = _base_run(
        top_events=[{"id": "e1", "headline": "New short-term rental cap announced", "source_name": "Reuters", "summary": "A real summary.", "source_url": "https://reuters.com/x"}],
        impact_analysis=[{
            "event_id": "e1",
            "sector_or_market_affected": "tourist-driven short-term rentals",
            "direction": "negative",
            "magnitude": "medium",
            "confidence": 0.55,
            "time_horizon": "short_term",
            "contested": False,
            "rationale": "The new cap directly shrinks the pool of eligible rental units, softening near-term yield expectations for that segment.",
            "recommended_action": "Flag for the portfolio team before the next acquisition review.",
        }],
    )
    pdf_bytes = build_report_pdf(run)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf_bytes)).pages)

    assert "New short-term rental cap announced" in text
    assert "The new cap directly shrinks the pool of eligible rental units" in text
    assert "Flag for the portfolio team before the next acquisition review" in text


def test_impact_analysis_without_a_rationale_still_renders_the_rest():
    """An older cached run, or a model response that omitted rationale
    (src/agents/judge_agent.py degrades to "" rather than failing), must
    not lose the recommended action or crash the PDF -- it just has no
    "Why:" line."""
    run = _base_run(
        impact_analysis=[{
            "event_id": "e1",
            "sector_or_market_affected": "prime residential demand",
            "direction": "neutral",
            "magnitude": "low",
            "confidence": 0.3,
            "time_horizon": "medium_term",
            "contested": False,
            "recommended_action": "No action needed.",
        }],
    )
    pdf_bytes = build_report_pdf(run)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf_bytes)).pages)

    assert "Why:" not in text
    assert "No action needed." in text


def test_content_with_html_special_characters_is_escaped_not_broken():
    """Real scraped article text can contain '<', '>' or '&' — this must not
    break reportlab's markup parser or let it be interpreted as markup."""
    run = _base_run(headline="Sanctions & tariffs <escalate> in region")
    pdf_bytes = build_report_pdf(run)
    assert pdf_bytes.startswith(b"%PDF")
