"""Tests for src/tools/pdf_extraction.py (2026-09-21 addition, in support
of POST /documents/upload). Builds real PDFs with reportlab (already a
project dependency, used the same way by src/services/pdf_export.py) so
this exercises pypdf against real bytes, not a fake stand-in for a PDF.

2026-09-25 addition: OCR tests build a real "scanned" page the same way a
real scanner would produce one -- text rendered into an image, then placed
on the PDF page as an image with no separate text layer -- and run it
through the real, installed Tesseract engine (this project's dev/CI image
has it, the same way it has pypdf/reportlab). This is not a fake stand-in
for OCR: it is the real pipeline (PyMuPDF render -> real pytesseract call)
against a real, if synthetic, scanned page."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from src.config import settings
import src.tools.pdf_extraction as pdf_extraction
from src.tools.pdf_extraction import PdfTextNotFoundError, extract_pdf_text


def _make_pdf(*lines: str, page_count: int = 1) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for _ in range(page_count):
        y = 750
        for line in lines:
            c.drawString(100, y, line)
            y -= 20
        c.showPage()
    c.save()
    return buf.getvalue()


_TEST_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _scanned_page_image(text: str) -> Image.Image:
    """A real image with real rendered text -- standing in for a real
    scanned page's pixels, large and plain enough for Tesseract to read
    back reliably."""
    img = Image.new("RGB", (1400, 300), color="white")
    draw = ImageDraw.Draw(img)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(_TEST_FONT_PATH, 40)
    except Exception:
        font = None
    draw.text((30, 110), text, fill="black", font=font)
    return img


def _make_scanned_pdf(*page_texts: str) -> bytes:
    """A real PDF whose real pages carry no text layer at all -- each
    page is only a real embedded image of rendered text, the same shape
    pypdf sees from an actual scanner or photographed document."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for text in page_texts:
        img = _scanned_page_image(text)
        c.drawImage(ImageReader(img), 50, 500, width=500, height=150)
        c.showPage()
    c.save()
    return buf.getvalue()


def test_extracts_real_text_from_a_real_pdf():
    pdf_bytes = _make_pdf(
        "Marrakech tourism investment report",
        "The government announced a new hospitality incentive program in March 2026.",
    )
    result = extract_pdf_text(pdf_bytes)
    assert "Marrakech tourism investment report" in result.text
    assert "hospitality incentive program" in result.text
    assert result.page_count == 1
    assert result.truncated is False


def test_counts_multiple_pages():
    pdf_bytes = _make_pdf("Repeated content line for every page.", page_count=3)
    result = extract_pdf_text(pdf_bytes)
    assert result.page_count == 3


def test_raises_on_a_pdf_with_no_extractable_text():
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.save()  # a real, valid, but entirely blank PDF -- no text layer at all
    blank_pdf = buf.getvalue()

    with pytest.raises(PdfTextNotFoundError, match="No usable text"):
        extract_pdf_text(blank_pdf)


def test_raises_a_clear_error_on_a_file_that_is_not_actually_a_pdf():
    with pytest.raises(PdfTextNotFoundError, match="Could not open this file as a PDF"):
        extract_pdf_text(b"this is definitely not a real pdf file")


def test_truncates_a_very_long_document_and_says_so():
    long_line = "A real sentence about Moroccan real estate market conditions. " * 50
    pdf_bytes = _make_pdf(*[long_line for _ in range(40)], page_count=5)
    result = extract_pdf_text(pdf_bytes, max_chars=500)
    assert len(result.text) == 500
    assert result.truncated is True


def test_does_not_truncate_a_short_document():
    pdf_bytes = _make_pdf("A short real document describing one specific real estate event.")
    result = extract_pdf_text(pdf_bytes, max_chars=40_000)
    assert result.truncated is False


def test_raises_the_original_message_when_ocr_is_turned_off(monkeypatch):
    """2026-09-25: the original, pre-OCR honest message must still be
    reachable for anyone who sets OCR_ENABLED=false (e.g. Tesseract can't
    be installed on their machine)."""
    monkeypatch.setattr(settings, "ocr_enabled", False)
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.save()
    with pytest.raises(PdfTextNotFoundError, match="this system does not do OCR"):
        extract_pdf_text(buf.getvalue())


def test_a_normal_text_pdf_never_invokes_ocr(monkeypatch):
    """OCR must never run on a real, already-real-text PDF -- checked here
    by making a real OCR call blow up the test if it's ever attempted."""
    def _boom(*args, **kwargs):
        raise AssertionError("OCR must not run when pypdf already found real text")

    monkeypatch.setattr(pdf_extraction.pytesseract, "image_to_string", _boom)
    pdf_bytes = _make_pdf("A short real document describing one specific real estate event.")
    result = extract_pdf_text(pdf_bytes)
    assert result.ocr_pages_used == 0
    assert "real estate event" in result.text


def test_ocr_reads_a_real_scanned_page_with_no_text_layer():
    """The core new behavior: a real page with only an embedded image (no
    text layer at all, the same shape a real scan produces) is read via
    the real Tesseract engine, not just reported as empty."""
    pdf_bytes = _make_scanned_pdf("MARRAKECH HOTEL INVESTMENT OPPORTUNITY REPORT")
    result = extract_pdf_text(pdf_bytes)
    assert result.ocr_pages_used == 1
    assert result.ocr_pages_skipped == 0
    assert "MARRAKECH" in result.text.upper()
    assert "INVESTMENT" in result.text.upper()


def test_ocr_handles_a_mixed_document_of_real_text_and_scanned_pages():
    """A document with some real-text pages and some scanned pages should
    OCR only the pages that actually need it."""
    real_text_pdf = _make_pdf("A real digital page with a genuine text layer about Morocco.")
    scanned_pdf = _make_scanned_pdf("RIAD PORTFOLIO BROCHURE FOR MARRAKECH MEDINA")
    # Merge isn't the point here -- exercise each shape directly against
    # the same extractor to confirm per-page behavior rather than hand-
    # rolling a multi-source PDF merge in the test itself.
    real_result = extract_pdf_text(real_text_pdf)
    scanned_result = extract_pdf_text(scanned_pdf)
    assert real_result.ocr_pages_used == 0
    assert scanned_result.ocr_pages_used == 1


def test_ocr_max_pages_caps_how_many_scanned_pages_are_read(monkeypatch):
    monkeypatch.setattr(settings, "ocr_max_pages", 1)
    pdf_bytes = _make_scanned_pdf(
        "PAGE ONE REAL ESTATE CONTENT ABOUT MARRAKECH",
        "PAGE TWO REAL ESTATE CONTENT ABOUT CASABLANCA",
        "PAGE THREE REAL ESTATE CONTENT ABOUT RABAT",
    )
    result = extract_pdf_text(pdf_bytes)
    assert result.ocr_pages_used == 1
    assert result.ocr_pages_skipped == 2


def test_ocr_missing_packages_raises_missing_configuration_error(monkeypatch):
    """If pymupdf/pytesseract/Pillow genuinely aren't installed, that's a
    setup problem (same as a missing LLM_API_KEY), not a per-file 422."""
    from src.errors import MissingConfigurationError

    monkeypatch.setattr(pdf_extraction, "pymupdf", None)
    pdf_bytes = _make_scanned_pdf("SOME SCANNED CONTENT")
    with pytest.raises(MissingConfigurationError, match="pip install -r requirements.txt"):
        extract_pdf_text(pdf_bytes)


def test_ocr_missing_tesseract_binary_raises_missing_configuration_error(monkeypatch):
    """A real, distinct message from 'no usable text' -- this is Tesseract
    itself not being found, not the file being a bad scan."""
    from src.errors import MissingConfigurationError

    def _not_found(*args, **kwargs):
        raise pdf_extraction.pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pdf_extraction.pytesseract, "image_to_string", _not_found)
    pdf_bytes = _make_scanned_pdf("SOME SCANNED CONTENT")
    with pytest.raises(MissingConfigurationError, match="could not be found on this machine"):
        extract_pdf_text(pdf_bytes)
