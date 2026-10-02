"""Extracts real text from an uploaded PDF (src/api/main.py's POST
/documents/upload) so the document agent (src/agents/document_agent.py)
has real content to analyze -- never fabricated, never guessed from the
filename alone.

pypdf (already a project dependency -- previously only used by
tests/test_pdf_export.py to verify pdf_export.py's own output) is reused
here as a real app dependency too: pure-Python, no external binary, so
nothing new to install beyond what `pip install -r requirements.txt`
already covers.

2026-09-25 addition, at Orchid Island's request after a real upload
turned out to be a genuine scan with no text layer: a page whose pypdf
text is too short to be real is rendered to an image (PyMuPDF -- pure
pip install, no external binary) and run through real OCR (pytesseract,
which wraps the real Tesseract engine -- see settings.ocr_* in
src/config/settings.py and .env.example for what to install and why).
This never runs on a normal, already-real-text PDF (checked page by page,
not "does this whole document look scanned"), so it costs nothing extra
for the common case. It also never invents anything: a page OCR still
finds no usable text stays exactly as empty as it would have been without
this addition.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Optional

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from src.config import settings
from src.errors import MissingConfigurationError

logger = logging.getLogger(__name__)

# Guarded import: OCR is a real, declared dependency (requirements.txt),
# but a missing install must degrade to one honest, actionable error
# (MissingConfigurationError, same "say exactly what's needed" standard as
# everywhere else in this project) rather than crashing the whole app at
# startup -- every other feature here (the daily pipeline, chat, etc.)
# has nothing to do with OCR and must keep working even if these two
# packages haven't been installed yet.
try:
    import pymupdf
    import pytesseract
    from PIL import Image

    _OCR_IMPORT_ERROR: Optional[str] = None
except ImportError as _exc:  # pragma: no cover -- exercised via monkeypatch in tests
    pymupdf = None  # type: ignore[assignment]
    pytesseract = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]
    _OCR_IMPORT_ERROR = str(_exc)

# A real page or two of extracted text, at minimum -- anything less is not
# enough to honestly analyze, and most often means the PDF has no real text
# layer at all (a scan) rather than a document that is genuinely this short.
_MIN_USABLE_CHARS = 40

# Per-page threshold for "this page needs OCR" -- a real page with fewer
# real characters than this is treated as image-only (a scanned page, a
# near-blank page, or a page whose text pypdf simply couldn't read), and is
# a candidate for OCR rather than being reported as-is.
_OCR_MIN_CHARS_PER_PAGE = 20

# Cap on how much extracted text this module returns at all (independent of
# how much of that src/services/llm_client.py then sends to the model --
# see DOCUMENT_TEXT_CHAR_LIMIT there). Keeps one huge upload from holding a
# request open indefinitely or bloating the saved JSON record.
_MAX_EXTRACTED_CHARS = 40_000


class PdfTextNotFoundError(RuntimeError):
    """Raised when a PDF has no usable extractable text -- most often a
    scanned/image-only PDF where OCR was either turned off or genuinely
    could not read the scan, or a corrupt/encrypted file this reader can't
    open. Not a MissingConfigurationError (nothing is misconfigured) and
    never silently swallowed -- the caller surfaces this exact message to
    whoever uploaded the file, instead of reporting a fabricated or an
    unexplained empty result."""


@dataclass(frozen=True)
class ExtractedPdf:
    text: str
    page_count: int
    truncated: bool
    # 2026-09-24 addition, at Orchid Island's request ("I need to know WHERE
    # in the PDF the information was found"): one real entry per real page
    # (page_texts[i] is page i+1's own text, empty string if that page had
    # none), kept alongside the concatenated `text` above so
    # src/agents/document_agent.py can build a page-marked version to send
    # the model and then VALIDATE whatever page number it reports against
    # this real list, rather than trusting an unchecked number.
    page_texts: list[str]
    # 2026-09-25 addition: how many real pages actually needed and got real
    # OCR text (as opposed to pypdf already finding real text), and how
    # many more needed it but were left as-is because ocr_max_pages was
    # reached -- both real counts, used by document_agent.py to add an
    # honest limitations entry, the same pattern `truncated` already uses.
    ocr_pages_used: int = 0
    ocr_pages_skipped: int = 0


def _ocr_page_text(doc, page_index: int) -> str:
    """Renders one real page to an image and runs real Tesseract OCR on
    it. Returns "" (never raises) for a single page's own rendering/OCR
    failure -- one malformed page must not fail the whole document, the
    same standard the pypdf loop below already applies."""
    try:
        pix = doc[page_index].get_pixmap(dpi=settings.ocr_dpi)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        return (pytesseract.image_to_string(image, lang=settings.ocr_languages) or "").strip()
    except pytesseract.TesseractNotFoundError:
        raise
    except Exception as exc:
        logger.warning("pdf_extraction: OCR failed on page %d: %s", page_index + 1, exc)
        return ""


def _apply_ocr(file_bytes: bytes, pages_text: list[str]) -> tuple[list[str], int, int]:
    """Real OCR fallback for real pages pypdf found little/no text on.
    Returns (updated pages_text, ocr_pages_used, ocr_pages_skipped).
    Raises MissingConfigurationError if OCR is turned on but genuinely
    can't run here (packages not installed, or the real Tesseract binary
    can't be found) -- that is a setup problem, not something wrong with
    this particular file, so it gets the same 503 "say exactly what's
    missing" treatment as a missing LLM_API_KEY, not a per-file 422."""
    candidates = [i for i, t in enumerate(pages_text) if len(t.strip()) < _OCR_MIN_CHARS_PER_PAGE]
    if not candidates or not settings.ocr_enabled:
        return pages_text, 0, 0

    if pymupdf is None or pytesseract is None or Image is None:
        raise MissingConfigurationError(
            "OCR is enabled (OCR_ENABLED=true) but the required packages are not installed "
            f"({_OCR_IMPORT_ERROR}). Run `pip install -r requirements.txt` to install pymupdf, "
            "pytesseract and Pillow, then restart the server."
        )
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    to_ocr = candidates[: settings.ocr_max_pages]
    skipped = len(candidates) - len(to_ocr)
    updated = list(pages_text)
    used = 0
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.warning("pdf_extraction: PyMuPDF could not open this file for OCR rendering: %s", exc)
        return pages_text, 0, len(candidates)

    try:
        for i in to_ocr:
            ocr_text = _ocr_page_text(doc, i)
            if len(ocr_text) > len(updated[i].strip()):
                updated[i] = ocr_text
                used += 1
    except pytesseract.TesseractNotFoundError as exc:
        raise MissingConfigurationError(
            "OCR is enabled (OCR_ENABLED=true) and the required Python packages are installed, but "
            "the real Tesseract OCR program could not be found on this machine. Install it (Windows: "
            "the UB-Mannheim build at https://github.com/UB-Mannheim/tesseract/wiki), then either add "
            "it to your PATH or set TESSERACT_CMD in .env to its full install path "
            f"(commonly \"C:\\Program Files\\Tesseract-OCR\\tesseract.exe\" on Windows). Original error: {exc}"
        ) from exc
    finally:
        doc.close()

    return updated, used, skipped


def extract_pdf_text(file_bytes: bytes, *, max_chars: int = _MAX_EXTRACTED_CHARS) -> ExtractedPdf:
    """Reads every real page's text layer via pypdf and concatenates it,
    then runs real OCR (see _apply_ocr) on whichever real pages came back
    with little or no text -- a fully scanned document gets every page
    OCR'd (up to settings.ocr_max_pages), a mixed document only gets its
    real scanned pages OCR'd, and a normal already-real-text PDF never
    touches OCR at all. Raises PdfTextNotFoundError if the file can't be
    opened at all, is password-protected, or the combined result (real
    pypdf text plus whatever OCR found) is still too little to honestly
    analyze. Truncates to max_chars for a very long document --
    ExtractedPdf.truncated tells the caller so it can report that
    honestly rather than silently analyzing only part of it."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except (PdfReadError, ValueError) as exc:
        raise PdfTextNotFoundError(f"Could not open this file as a PDF: {exc}") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")  # only unlocks a PDF encrypted with an empty user password
        except Exception:
            pass
    if reader.is_encrypted:
        raise PdfTextNotFoundError(
            "This PDF is password-protected -- remove the password and re-upload it."
        )

    pages_text: list[str] = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception as exc:  # one malformed page must not fail the whole document
            logger.warning("pdf_extraction: failed to extract one page: %s", exc)
            pages_text.append("")

    pages_text, ocr_pages_used, ocr_pages_skipped = _apply_ocr(file_bytes, pages_text)

    full_text = "\n\n".join(t for t in pages_text if t.strip())
    if len(full_text.strip()) < _MIN_USABLE_CHARS:
        if not settings.ocr_enabled:
            raise PdfTextNotFoundError(
                "No usable text could be found in this PDF -- it may be a scanned image "
                "without a text layer (this system does not do OCR), or the pages are empty."
            )
        raise PdfTextNotFoundError(
            "No usable text could be found in this PDF, even after attempting OCR on its scanned "
            "pages -- the scan quality may be too poor to read (blurry, skewed, very low resolution), "
            "or the pages are genuinely empty."
        )

    truncated = len(full_text) > max_chars
    return ExtractedPdf(
        text=full_text[:max_chars],
        page_count=len(reader.pages),
        truncated=truncated,
        page_texts=pages_text,
        ocr_pages_used=ocr_pages_used,
        ocr_pages_skipped=ocr_pages_skipped,
    )
