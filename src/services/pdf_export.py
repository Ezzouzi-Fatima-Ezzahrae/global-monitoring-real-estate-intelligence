"""Renders one run's DailyReport (see src/models/report.py) as a real,
downloadable PDF -- so a digest can be saved, printed, or emailed outside
the browser GUI. Wired to GET /runs/{run_id}/pdf in src/api/main.py, and to
a "Download PDF" link in the local GUI (src/api/static/index.html).

Built directly from the same structured fields every other view already
uses (headline, top_events, debate_highlights, impact_analysis,
risks_and_opportunities, recommended_actions, limitations, citations) --
not a naive markdown-to-PDF conversion of report_markdown.

Uses reportlab (pure-Python; no external binary like wkhtmltopdf or pandoc
required), consistent with this project's "one `pip install`, nothing else
to install" scope.
"""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# The same emblem used in the GUI header (src/api/static/index.html's
# .brand-mark) and as the app's favicon -- one logo asset, reused everywhere
# rather than redrawn per output. Missing gracefully: if this file isn't
# there (e.g. an old checkout from before the logo was added), the PDF
# still builds fine, just without the image cell.
_LOGO_PATH = Path(__file__).resolve().parents[2] / "src" / "api" / "static" / "logo.png"

# Same terracotta/ink palette as the GUI (src/api/static/index.html --ink
# / --accent) and the delivered architecture report, for visual continuity
# across every Orchid Island deliverable this project produces.
_ACCENT = colors.HexColor("#B0532A")
_INK = colors.HexColor("#2A231D")
_MUTED = colors.HexColor("#6B6055")
_LINE = colors.HexColor("#D8CFC0")


def _esc(text) -> str:
    """reportlab's Paragraph parses a small HTML-like markup subset -- real
    scraped article text can contain '<', '>' or '&', so escape it rather
    than trust it, the same prompt-injection-adjacent caution the LLM
    client (src/services/llm_client.py) already applies to this content."""
    return str(text if text is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("OI_H1", parent=base["Heading1"], textColor=_ACCENT, fontName="Helvetica-Bold", fontSize=18, spaceAfter=6, leading=22),
        "h2": ParagraphStyle("OI_H2", parent=base["Heading2"], textColor=_ACCENT, fontName="Helvetica-Bold", fontSize=12.5, spaceBefore=16, spaceAfter=6, leading=16),
        "meta": ParagraphStyle("OI_Meta", parent=base["BodyText"], textColor=_MUTED, fontSize=8.5, leading=12),
        "body": ParagraphStyle("OI_Body", parent=base["BodyText"], textColor=_INK, fontSize=10.5, leading=15),
        "headline": ParagraphStyle("OI_Headline", parent=base["BodyText"], textColor=_INK, fontName="Helvetica-BoldOblique", fontSize=13, leading=18, spaceAfter=4),
    }


def _bulleted_section(story, styles, title, items):
    if not items:
        return
    story.append(Paragraph(title, styles["h2"]))
    story.append(
        ListFlowable(
            [ListItem(Paragraph(item, styles["body"]), leftIndent=10) for item in items],
            bulletType="bullet",
            bulletColor=_ACCENT,
            leftIndent=14,
            spaceBefore=2,
        )
    )


def build_report_pdf(run: dict) -> bytes:
    """`run` is the same full run dict src/api/main.py already serializes
    (_serialize_run / what GET /runs/{id} returns as JSON) -- this reads
    its run_id/generated_at/run_date and `report` fields only."""
    report = run.get("report") or {}
    styles = _styles()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2.2 * cm, bottomMargin=2 * cm, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        title=f"Daily Intelligence Report — {report.get('report_date') or run.get('run_date', '')}",
    )

    letterhead_text = [
        Paragraph(f"Daily Intelligence Report — {_esc(report.get('report_date') or run.get('run_date', ''))}", styles["h1"]),
        Paragraph(f"Orchid Island — Global Monitoring &amp; Real Estate Intelligence System", styles["meta"]),
        Paragraph(f"Run {_esc(run.get('run_id', ''))} · generated {_esc(run.get('generated_at', ''))}", styles["meta"]),
    ]
    if _LOGO_PATH.exists():
        logo = Image(str(_LOGO_PATH), width=1.6 * cm, height=1.6 * cm)
        letterhead = Table(
            [[logo, letterhead_text]],
            colWidths=[2.1 * cm, None],
        )
        letterhead.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story = [letterhead]
    else:
        story = letterhead_text

    story.append(HRFlowable(width="100%", thickness=0.75, color=_LINE, spaceBefore=8, spaceAfter=12))

    if not report:
        failed = [s.get("agent") for s in run.get("trace", []) if s.get("status") == "failed"]
        story.append(Paragraph(
            "This run did not produce a report."
            + (f" Failed step(s): {_esc(', '.join(failed))}." if failed else " See the pipeline trace for what failed."),
            styles["body"],
        ))
    else:
        story.append(Paragraph(_esc(report.get("headline", "")), styles["headline"]))
        if report.get("no_significant_events"):
            story.append(Spacer(1, 6))
            story.append(Paragraph("No significant events were found today that warrant a notable update.", styles["body"]))
        else:
            events = report.get("top_events") or run.get("events") or []
            _bulleted_section(story, styles, "Top Events", [
                f"<b>{_esc(e.get('headline',''))}</b> ({_esc(e.get('source_name') or e.get('source_url',''))}) — {_esc(e.get('summary',''))}"
                for e in events
            ])
            _bulleted_section(story, styles, "Debate Highlights", [_esc(d) for d in report.get("debate_highlights", [])])
            # event_id -> headline, so each impact line says *which* event it's
            # about instead of only its sector/direction/magnitude -- without
            # this, "prime residential demand, negative/medium" reads as an
            # abstract market call rather than something traceable back to a
            # specific, sourced event above it in the same report.
            headline_by_event_id = {e.get("id"): e.get("headline", "") for e in events}

            def _impact_line(ia: dict) -> str:
                # Same "verdict numbers, then the why, then the action" shape
                # as the GUI's impact-box (src/api/static/index.html) -- the
                # PDF is the version of this report that leaves the machine
                # (emailed, printed), so it needs the same real explanation,
                # not just the numbers. rationale is omitted (not a blank
                # "Why:" line) when the model response didn't include one --
                # see src/agents/judge_agent.py's fail-gracefully-per-field note.
                head = (
                    f"<b>{_esc(headline_by_event_id.get(ia.get('event_id'), ia.get('event_id', '')))}</b> — "
                    f"[{_esc(ia.get('sector_or_market_affected',''))}] {_esc(ia.get('direction',''))}/{_esc(ia.get('magnitude',''))}, "
                    f"confidence {ia.get('confidence', 0):.2f}, horizon {_esc(ia.get('time_horizon',''))}"
                    f"{' (CONTESTED)' if ia.get('contested') else ''}"
                )
                rationale = ia.get("rationale")
                if rationale:
                    head += f"<br/><i>Why:</i> {_esc(rationale)}"
                if ia.get("recommended_action"):
                    head += f"<br/><i>Recommended action:</i> {_esc(ia.get('recommended_action'))}"
                return head

            _bulleted_section(story, styles, "Real Estate Impact Analysis", [
                _impact_line(ia) for ia in report.get("impact_analysis", [])
            ])
            _bulleted_section(story, styles, "Risks &amp; Opportunities", [_esc(r) for r in report.get("risks_and_opportunities", [])])
            _bulleted_section(story, styles, "Recommended Actions", [_esc(a) for a in report.get("recommended_actions", [])])
            _bulleted_section(story, styles, "Confidence &amp; Limitations", [_esc(l) for l in report.get("limitations", [])])
            _bulleted_section(story, styles, "Sources", [_esc(c) for c in report.get("citations", [])])

    doc.build(story)
    return buf.getvalue()
