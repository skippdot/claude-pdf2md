from __future__ import annotations

import os
import sys
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_pdf(tmp_path):
    def _build(pages: list[dict]) -> Path:
        doc = fitz.open()
        for page_spec in pages:
            page = doc.new_page(width=595, height=842)
            for item in page_spec.get("text", []):
                point = fitz.Point(item["x"], item["y"])
                fontsize = item.get("size", 11)
                fontname = item.get("font", "Helvetica")
                page.insert_text(
                    point,
                    item["text"],
                    fontname=fontname,
                    fontsize=fontsize,
                )
            for link in page_spec.get("links", []):
                rect = fitz.Rect(*link["rect"])
                page.insert_link({"kind": fitz.LINK_URI, "from": rect, "uri": link["uri"]})
        path = tmp_path / "synth.pdf"
        doc.save(str(path))
        doc.close()
        return path
    return _build


@pytest.fixture(scope="session")
def bulgaria_watch_pdf() -> Path:
    candidate = Path(
        "/Users/skipp/Downloads/"
        "Bulgaria Watch #40-#49_ 10 New Investigations on Migrant Rights, "
        "State Failures and EU Compliance.pdf"
    )
    if candidate.is_file():
        return candidate
    override = os.environ.get("CLAUDE_PDF2MD_FIXTURE")
    if override and Path(override).is_file():
        return Path(override)
    pytest.skip("Bulgaria Watch PDF fixture not available on this machine.")
