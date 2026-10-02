"""User-uploaded-document analysis (2026-09-21 addition, at Orchid
Island's request: "a place in my digital console where I upload some pdf
... and from those pdfs u take data and also extracts from them the
events that can affect real estate in Morocco").

Deliberately kept separate from the automated daily pipeline
(src/orchestrator/graph.py) — confirmed directly with Orchid Island: an
uploaded document is analyzed the moment it's uploaded, on its own, not
folded into that day's debate / impact-assessment / priority-ranking run
(that would also re-trigger the debate stage's extra LLM calls on every
upload, which nothing here needs). It still reuses the exact same Event
schema and the same no-fabrication contract as every monitoring agent
(src/agents/monitoring_agent.py): extraction is always grounded in the
document's own real, extracted text (src/tools/pdf_extraction.py), never
invented, and each event's source_url points back to the uploaded PDF
itself (served by GET /documents/{document_id}/pdf), so any claim can be
checked against the original file the same way a news event can be
checked against its article.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from src.models import Event, EventEntities, PdfReference
from src.services.llm_client import DOCUMENT_TEXT_CHAR_LIMIT, llm_client
from src.services.source_classification import classify_pdf_source
from src.tools.pdf_extraction import ExtractedPdf, PdfTextNotFoundError, extract_pdf_text

logger = logging.getLogger(__name__)

DOCUMENT_AGENT_NAME = "Uploaded Document Agent"

__all__ = ["DOCUMENT_AGENT_NAME", "analyze_uploaded_pdf", "PdfTextNotFoundError"]


def _with_quote(interpretation: str, quote: Optional[str]) -> str:
    if not quote or not quote.strip():
        return interpretation
    return f'{interpretation}\n\nFrom the document: "{quote.strip()}"'


def _build_marked_text(page_texts: list[str]) -> str:
    """Inserts a real, explicit page marker before each real page's own
    text, so the model can honestly report which page it read something
    on. That report is then checked against page_texts itself (see
    _verify_page_reference), never trusted unchecked. Pages with no
    extractable text are skipped here (nothing to mark), the same way the
    plain concatenation in src/tools/pdf_extraction.py already drops
    them."""
    parts = [f"[PAGE {i}]\n{page_text}" for i, page_text in enumerate(page_texts, start=1) if page_text.strip()]
    return "\n\n".join(parts)


def _verify_page_reference(
    raw: dict, *, page_texts: list[str], page_count: int
) -> tuple[Optional[int], Optional[str]]:
    """Returns (page, section), each either a real, checked value or None —
    never the model's unchecked claim. `page` is kept only if it is an
    integer inside this document's real page range. `section` is kept only
    if it is also a real, verbatim substring of that specific page's own
    extracted text (case-insensitive) — a plausible-sounding heading the
    model invented, or one that belongs to a different page, is dropped
    rather than shown as if it were confirmed."""
    page = raw.get("page")
    if not isinstance(page, int) or not (1 <= page <= page_count):
        return None, None
    page_text = page_texts[page - 1] if page - 1 < len(page_texts) else ""
    section = raw.get("section")
    if isinstance(section, str) and section.strip() and section.strip().lower() in page_text.lower():
        return page, section.strip()
    return page, None


def analyze_uploaded_pdf(file_bytes: bytes, *, filename: str, source_url: str, document_id: str) -> dict:
    """Extracts the PDF's real text and asks the LLM to find every real,
    grounded, real-estate-relevant event actually described in it.
    Returns {"events": list[Event], "page_count": int,
    "limitations": list[str]}.

    Raises PdfTextNotFoundError (propagated from extract_pdf_text, not
    caught here) when the file has no usable text — e.g. a scanned image
    with no text layer — so the caller (POST /documents/upload) can
    surface that as an honest 4xx with the real reason, the same standard
    src/errors.py's MissingConfigurationError sets for every other missing
    prerequisite in this project. MissingConfigurationError itself (from
    llm_client.extract_events_from_document, if LLM_API_KEY isn't set) is
    likewise not caught here — it propagates for the same reason.

    2026-09-24 addition: every extracted event now also carries a
    PdfReference (document_id plus a page/section that were independently
    verified against this document's own real text — see
    _verify_page_reference above), so Orchid Island can open the PDF and
    check exactly where an event came from, not just that it came from
    "the PDF".
    """
    extracted: ExtractedPdf = extract_pdf_text(file_bytes)

    text = extracted.text
    limitations: list[str] = []
    if extracted.ocr_pages_used:
        limitations.append(
            f"{extracted.ocr_pages_used} page(s) of this document had no real text layer (a scan) "
            "and were read with OCR instead. OCR text can occasionally misread a word or number, so "
            "treat those pages' details as slightly less certain than a page with a real text layer."
        )
    if extracted.ocr_pages_skipped:
        limitations.append(
            f"{extracted.ocr_pages_skipped} more scanned page(s) were not OCR'd (the "
            "OCR_MAX_PAGES limit was reached) and so were not analyzed. Raise OCR_MAX_PAGES in .env "
            "to cover them, though a bigger scan takes proportionally longer to process."
        )
    if extracted.truncated:
        limitations.append(
            f"This document is long ({extracted.page_count} pages): only the first "
            f"{len(text):,} characters of its extracted text were kept."
        )
    if len(text) > DOCUMENT_TEXT_CHAR_LIMIT:
        limitations.append(
            f"Only the first {DOCUMENT_TEXT_CHAR_LIMIT:,} characters were sent to the AI model for "
            "analysis. A very long document may describe relevant events beyond that point that "
            "were not analyzed."
        )

    marked_text = _build_marked_text(extracted.page_texts)
    raw_events = llm_client.extract_events_from_document(
        agent_name=DOCUMENT_AGENT_NAME,
        document_title=filename,
        document_text=marked_text,
        source_url=source_url,
    )

    events: list[Event] = []
    for raw in raw_events:
        try:
            # Same standard as every monitoring agent (2026-09-17, at
            # Orchid Island's request): "low" relevance means genuinely
            # not useful, so it's skipped here rather than shown as noise
            # — not just a differently-colored pill.
            if raw.get("relevance_to_real_estate") == "low":
                logger.info(
                    "document_agent: skipping an extracted item from %s, judged low relevance", filename
                )
                continue
            page, section = _verify_page_reference(
                raw, page_texts=extracted.page_texts, page_count=extracted.page_count
            )
            source_type, source_quality = classify_pdf_source(page_verified=page is not None)
            events.append(
                Event(
                    id=str(uuid.uuid4()),
                    agent=DOCUMENT_AGENT_NAME,
                    headline=raw["headline"],
                    summary=raw["summary"],
                    entities=EventEntities(),
                    sentiment=raw.get("sentiment", "neutral"),
                    relevance_to_real_estate=raw.get("relevance_to_real_estate", "medium"),
                    confidence=raw.get("confidence", 0.0),
                    source_url=source_url,
                    source_name=f"Uploaded document — {filename}",
                    # Honest default: an uploaded document's real publish/
                    # event date is not reliably known from the file alone
                    # (unlike a news article's byline or a video's
                    # publishedAt) — None rather than a guessed date.
                    published_at=None,
                    agent_interpretation=_with_quote(raw.get("agent_interpretation", ""), raw.get("supporting_quote")),
                    retrieval_id=str(uuid.uuid4()),
                    source_type=source_type,
                    source_quality=source_quality,
                    pdf_reference=PdfReference(document_id=document_id, page=page, section=section),
                )
            )
        except Exception as exc:  # one malformed extracted item must not lose every other real event
            logger.error("document_agent: failed to build Event from extracted item %r: %s", raw, exc)
            continue

    logger.info("%s produced %d event(s) from %s", DOCUMENT_AGENT_NAME, len(events), filename)
    return {"events": events, "page_count": extracted.page_count, "limitations": limitations}
