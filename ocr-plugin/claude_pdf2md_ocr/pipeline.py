"""End-to-end OCR + markdown conversion pipeline.

This module composes the base `claude-pdf2md` submodules by hand — it does
NOT go through `claude_pdf2md.convert_to_string` — because the base package
doesn't yet expose a post-extract hook. Once the base ships an
`enrichers=` seam, `convert_with_ocr` will collapse to:

    return convert_to_string(pdf_path, enrichers=[OcrEnricher(...)])

Until then, the explicit composition lives here."""

from __future__ import annotations

from pathlib import Path

import fitz
from claude_pdf2md import emit, extract, images, structure, tables
from claude_pdf2md.model import Doc, ImageAnnot, Page

from .backends import OcrBackend, OcrWord
from .backends.tesseract import TesseractBackend
from .inject import words_to_blocks
from .spellcheck import fix_word, languages_for

_DEFAULT_DPI = 200  # Tesseract's sweet spot for small body text on A4 scans.


def convert_with_ocr(
    pdf_path: str | Path,
    output: str | Path | None = None,
    assets_dir: str | Path | None = None,
    include_title: bool = False,
    lang: str = "ukr+rus+eng",
    only_empty_pages: bool = True,
    min_confidence: float = 0.5,
    backend: OcrBackend | None = None,
    dpi: int = _DEFAULT_DPI,
    spellcheck: bool = True,
) -> str:
    backend = backend or TesseractBackend()
    pdf_path = str(pdf_path)
    assets_path = Path(assets_dir) if assets_dir is not None else None

    mu, doc = extract.extract_doc(pdf_path)
    try:
        _run_ocr(mu, doc, backend, lang, dpi, min_confidence, only_empty_pages, spellcheck)
        tables.apply_tables(mu, doc)
        images.write_assets(doc, assets_path)
        structure.analyze_document(doc)
        md = emit.render(doc, include_title=include_title)
    finally:
        mu.close()

    if output is not None:
        Path(output).write_text(md, encoding="utf-8")
    return md


def _run_ocr(
    mu: fitz.Document,
    doc: Doc,
    backend: OcrBackend,
    lang: str,
    dpi: int,
    min_confidence: float,
    only_empty_pages: bool,
    spellcheck: bool,
) -> None:
    for pno, page in enumerate(doc.pages):
        if only_empty_pages and _has_text(page):
            continue
        mu_page = mu.load_page(pno)
        png_bytes = mu_page.get_pixmap(dpi=dpi).tobytes("png")
        words = backend.recognise(
            image_bytes=png_bytes,
            pdf_width_pt=page.width,
            pdf_height_pt=page.height,
            dpi=dpi,
            lang=lang,
        )
        if not words:
            continue
        if spellcheck:
            words = _apply_spellcheck(words)
        page.blocks = words_to_blocks(words, min_confidence=min_confidence)
        # Preserve inline images (logos, stamps, QR codes) but drop whole-page
        # rasters — on an OCR'd page those are just a picture of the same text
        # we just recognised, and keeping both doubles the output size.
        # Filter `page.images` directly because `images.write_assets` hasn't
        # turned them into image-kind Blocks yet; doing it here keeps the
        # assets directory free of the redundant full-page PNG as well.
        page.images = [img for img in page.images if not _is_whole_page_image(img, page)]


def _apply_spellcheck(words: list[OcrWord]) -> list[OcrWord]:
    """Per-page cross-script and known-misread fixup.

    We look at the whole page's OCR output to pick a per-page dominant-language
    tuple, then run each word through `fix_word`. A word only gets replaced when
    the correction is both cross-script-distinguishable AND a valid entry in the
    target-language frequency dictionary — so proper nouns, product names, IDs,
    and numeric tokens flow through unchanged.
    """
    page_text = " ".join(w.text for w in words)
    langs = languages_for(page_text)
    return [
        OcrWord(
            text=fix_word(w.text, langs),
            x0=w.x0,
            y0=w.y0,
            x1=w.x1,
            y1=w.y1,
            confidence=w.confidence,
            line_id=w.line_id,
        )
        for w in words
    ]


def _is_whole_page_image(img: ImageAnnot, page: Page) -> bool:
    if page.width <= 0 or page.height <= 0:
        return False
    img_area = (img.bbox.x1 - img.bbox.x0) * (img.bbox.y1 - img.bbox.y0)
    page_area = page.width * page.height
    return img_area / page_area > 0.8


def _has_text(page: Page) -> bool:
    """Decide whether a page already has a usable text layer, so OCR can skip it.

    Hybrid scans are common in legal PDFs: the page is a rasterised scan with
    just a handful of overlay URLs or signature strings sitting on top of it.
    If we detect a whole-page image, we demand meaningful body text (>=200
    characters of real content, excluding image-kind blocks) before trusting
    the text layer — otherwise OCR is what actually recovers the content.
    """
    text_chars = sum(len(line.text.strip()) for block in page.blocks if block.kind != "image" for line in block.lines)
    has_whole_page_image = any(_is_whole_page_image(img, page) for img in page.images)
    min_chars = 200 if has_whole_page_image else 1
    return text_chars >= min_chars
