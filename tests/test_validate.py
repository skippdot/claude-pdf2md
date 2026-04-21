"""Tests for `validate_doc` and the `validate=True` convert-time flag."""

from __future__ import annotations

import warnings
from pathlib import Path

import fitz
import pytest

from claude_pdf2md import (
    PdfStructureWarning,
    ValidationIssue,
    convert_to_string,
    validate_doc,
)
from claude_pdf2md.model import BBox, Block, Doc, Line, Page, Span


def _span(text: str, size: float = 11.0) -> Span:
    return Span(text=text, bbox=BBox(0, 0, 1, 1), size=size, font="Arial", flags=0, color=0)


def _line(text: str, size: float = 11.0) -> Line:
    return Line(spans=[_span(text, size)], bbox=BBox(0, 0, 1, 1))


def _paragraph(text: str) -> Block:
    return Block(kind="paragraph", lines=[_line(text)])


def _heading(text: str, level: int) -> Block:
    return Block(kind="heading", lines=[_line(text, size=18)], level=level)


def _image_block() -> Block:
    return Block(kind="image", image_path="scan.png")


def _page(number: int, blocks: list[Block]) -> Page:
    return Page(number=number, width=595, height=842, blocks=blocks)


def test_empty_page_flagged():
    doc = Doc(pages=[_page(1, [])])
    issues = validate_doc(doc)
    assert [i.code for i in issues] == ["empty_page"]
    assert issues[0].page_number == 1


def test_image_only_page_flagged():
    doc = Doc(pages=[_page(1, [_image_block()])])
    issues = validate_doc(doc)
    assert [i.code for i in issues] == ["text_free_page_with_image"]
    assert "claude-pdf2md-ocr" in issues[0].message


def test_heading_level_jump_flagged():
    doc = Doc(pages=[_page(1, [_heading("Title", 1), _heading("Deep", 3)])])
    issues = validate_doc(doc)
    assert [i.code for i in issues] == ["heading_level_jump"]
    assert "H1 to H3" in issues[0].message


def test_clean_doc_produces_no_issues():
    doc = Doc(
        pages=[
            _page(
                1,
                [
                    _heading("Title", 1),
                    _heading("Subsection", 2),
                    _paragraph("Body text."),
                ],
            )
        ]
    )
    assert validate_doc(doc) == []


def test_image_plus_text_is_not_flagged():
    # A page with both a logo and real body text is a normal native PDF page,
    # not an un-OCR'd scan.
    doc = Doc(pages=[_page(1, [_image_block(), _paragraph("Real body copy.")])])
    assert validate_doc(doc) == []


def test_validation_issue_is_hashable():
    # frozen=True implies hashable — let callers dedupe issues in a set.
    issue = ValidationIssue(code="x", page_number=1, message="msg")
    assert {issue, issue} == {issue}


@pytest.fixture
def native_pdf(tmp_path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(72, 80), "Native Heading", fontname="Helvetica-Bold", fontsize=18)
    page.insert_text(fitz.Point(72, 140), "Body paragraph.", fontname="Helvetica", fontsize=11)
    path = tmp_path / "native.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_convert_with_validate_false_is_silent(native_pdf: Path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        convert_to_string(native_pdf, validate=False)
    assert not any(issubclass(w.category, PdfStructureWarning) for w in caught)


def test_convert_with_validate_true_on_clean_pdf_also_silent(native_pdf: Path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        convert_to_string(native_pdf, validate=True)
    assert not any(issubclass(w.category, PdfStructureWarning) for w in caught)


def test_convert_with_validate_true_emits_warning_on_empty_pdf(tmp_path: Path):
    # A zero-content page triggers `empty_page`; proves the flag is plumbed
    # into the pipeline end-to-end, not just unit-tested in isolation.
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    path = tmp_path / "empty.pdf"
    doc.save(str(path))
    doc.close()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        convert_to_string(path, validate=True)
    structural = [w for w in caught if issubclass(w.category, PdfStructureWarning)]
    assert structural, "expected a PdfStructureWarning for an empty PDF"
    assert "empty_page" in str(structural[0].message)
