"""Tests for the `enrichers=` hook in convert_to_string.

These verify the public contract advertised in `PageEnricher`: an enricher
is called once per page with `(mu_page, page)`, any mutations it makes to
`page.blocks` survive into the final Markdown output, and omitting the
parameter (or passing an empty list) keeps the pipeline identical to a
plain conversion."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from claude_pdf2md import PageEnricher, convert_to_string
from claude_pdf2md.model import BBox, Block, Line, Page, Span


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


class _AppendingEnricher:
    """Adds a known marker block to every page — proves the hook ran and
    its mutations reached the emitter."""

    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.calls = 0

    def enrich(self, mu_page: fitz.Page, page: Page) -> None:
        self.calls += 1
        bbox = BBox(72, 500, 300, 516)
        span = Span(
            text=self.marker,
            bbox=bbox,
            size=11,
            font="Helvetica",
            flags=0,
            color=0,
            url=None,
        )
        page.blocks.append(Block(kind="paragraph", lines=[Line(spans=[span], bbox=bbox)], bbox=bbox))


def test_enricher_is_called_once_per_page_and_mutations_reach_output(native_pdf: Path):
    enricher = _AppendingEnricher("ENRICHER_MARKER_XYZZY")
    md = convert_to_string(native_pdf, enrichers=[enricher])
    assert enricher.calls == 1  # single-page fixture
    assert "ENRICHER_MARKER_XYZZY" in md
    # Native content still emerges — enricher augments, doesn't replace.
    assert "Native Heading" in md
    assert "Body paragraph." in md


def test_no_enrichers_is_identical_to_plain_call(native_pdf: Path):
    baseline = convert_to_string(native_pdf)
    via_none = convert_to_string(native_pdf, enrichers=None)
    via_empty = convert_to_string(native_pdf, enrichers=[])
    assert baseline == via_none == via_empty


def test_multiple_enrichers_run_in_order(native_pdf: Path):
    first = _AppendingEnricher("FIRST_MARK")
    second = _AppendingEnricher("SECOND_MARK")
    md = convert_to_string(native_pdf, enrichers=[first, second])
    # Both markers land; their order in page.blocks follows registration order.
    assert "FIRST_MARK" in md
    assert "SECOND_MARK" in md
    assert md.index("FIRST_MARK") < md.index("SECOND_MARK")


def test_page_enricher_protocol_satisfied_structurally(native_pdf: Path):
    # A plain object with an `enrich` method must count as a PageEnricher
    # without needing to inherit from the Protocol class.
    class _Bare:
        def enrich(self, mu_page, page):
            pass

    enricher: PageEnricher = _Bare()
    assert convert_to_string(native_pdf, enrichers=[enricher])  # no exception
