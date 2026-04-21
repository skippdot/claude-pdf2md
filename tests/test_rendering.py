"""Coverage for the visual-diff path without an external fixture.

The `render_diff` pipeline (and the `render_pdf_*` helpers it depends on)
is only exercised end-to-end by the Bulgaria-Watch integration test, which
relies on a local PDF that isn't — and can't be — shipped in the repo. This
module builds a small synthetic PDF from the project's own MD→PDF fixture,
converts it back to Markdown, and then diffs the two, which touches every
public function in `claude_pdf2md.rendering` at least once.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_pdf2md import convert_to_string

SAMPLE_MD = """# Diff Coverage Fixture

A short, deterministic document used to exercise the rendering pipeline in
a hermetic test environment. See [project docs](https://example.com/docs).

## Section Two

- bullet one
- bullet two with a [link](https://example.com/two)
- bullet three

Closing paragraph with **bold emphasis** and more prose so that the rendered
page has enough body text to produce a meaningful SSIM score.
"""


def test_render_diff_runs_end_to_end_on_synthetic_pdf(md_to_pdf, tmp_path: Path):
    pytest.importorskip("weasyprint")
    pytest.importorskip("markdown_it")
    from claude_pdf2md.rendering import render_diff

    source_pdf = md_to_pdf(SAMPLE_MD)
    reconstructed_md = convert_to_string(source_pdf)

    out_dir = tmp_path / "diff"
    report = render_diff(source_pdf, reconstructed_md, out_dir)

    assert report["compared"] >= 1
    assert report["pdf_pages"] >= 1
    assert report["md_pages"] >= 1
    assert 0.0 <= report["mean_ssim"] <= 1.0
    assert (out_dir / "report.json").is_file()
    assert (out_dir / "page_001.diff.png").is_file()


def test_render_pdf_pages_returns_one_image_per_page(md_to_pdf):
    pytest.importorskip("weasyprint")
    from claude_pdf2md.rendering import render_pdf_pages

    pdf = md_to_pdf("# Just one page\n\nBody text.\n")
    pages = render_pdf_pages(pdf, dpi=100)
    assert len(pages) >= 1
    assert pages[0].size[0] > 0 and pages[0].size[1] > 0


def test_render_pdf_bytes_pages_matches_file_variant(md_to_pdf):
    pytest.importorskip("weasyprint")
    from claude_pdf2md.rendering import render_pdf_bytes_pages, render_pdf_pages

    pdf_path = md_to_pdf("# Bytes vs file\n\nBody.\n")
    from_file = render_pdf_pages(pdf_path, dpi=100)
    from_bytes = render_pdf_bytes_pages(pdf_path.read_bytes(), dpi=100)
    assert len(from_file) == len(from_bytes)
    assert from_file[0].size == from_bytes[0].size
