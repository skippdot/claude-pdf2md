"""Smoke tests with a stub OCR backend — no Tesseract binary required.

Verifies that `convert_with_ocr` composes the base `claude-pdf2md` pipeline
correctly: a stub backend that returns a fixed set of `OcrWord`s for any
image input must produce a Markdown document that contains those words."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from claude_pdf2md_ocr import convert_with_ocr
from claude_pdf2md_ocr.backends import OcrBackend, OcrWord


class _StubBackend(OcrBackend):
    """Pretends to recognise two hard-coded words on every page."""

    def __init__(self, words: list[OcrWord]) -> None:
        self._words = words

    def recognise(
        self,
        image_bytes: bytes,
        pdf_width_pt: float,
        pdf_height_pt: float,
        dpi: int,
        lang: str,
    ) -> list[OcrWord]:
        return self._words


def _make_scanned_pdf(tmp_path: Path) -> Path:
    """Build a minimal PDF whose single page has no text layer — just a
    full-page image that survives PyMuPDF's text-layer extraction as empty."""
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    png = buf.getvalue()

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(10, 10, 585, 832), stream=png)
    path = tmp_path / "scanned.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_stub_backend_fills_empty_page(tmp_path: Path):
    pdf = _make_scanned_pdf(tmp_path)
    words = [
        OcrWord(text="Hello", x0=72, y0=72, x1=120, y1=88, confidence=0.95, line_id=1),
        OcrWord(text="World", x0=130, y0=72, x1=180, y1=88, confidence=0.93, line_id=1),
    ]

    md = convert_with_ocr(pdf, backend=_StubBackend(words), lang="eng", min_confidence=0.0)

    assert "Hello" in md
    assert "World" in md


def test_empty_ocr_result_leaves_page_empty(tmp_path: Path):
    pdf = _make_scanned_pdf(tmp_path)
    md = convert_with_ocr(pdf, backend=_StubBackend([]), lang="eng")
    # The stub returned nothing, so no OCR words land in the output. The page
    # still contains the embedded full-page image which gets filtered out
    # because it's >80% of page area, leaving essentially an empty body.
    assert "Hello" not in md
    assert "World" not in md


def test_rejects_missing_input(tmp_path: Path):
    with pytest.raises((FileNotFoundError, RuntimeError)):
        convert_with_ocr(tmp_path / "does-not-exist.pdf", backend=_StubBackend([]))
