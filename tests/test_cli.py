"""CLI smoke tests — verify argument parsing and the public entry points."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from claude_pdf2md.cli import main


@pytest.fixture
def tiny_pdf(tmp_path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(72, 80), "CLI Heading", fontname="Helvetica-Bold", fontsize=18)
    page.insert_text(fitz.Point(72, 140), "Body paragraph.", fontname="Helvetica", fontsize=11)
    path = tmp_path / "tiny.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_cli_writes_markdown_to_output_file(tiny_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.md"
    rc = main([str(tiny_pdf), "-o", str(out)])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "CLI Heading" in text
    assert "Body paragraph." in text


def test_cli_rejects_missing_input(tmp_path: Path, capsys):
    rc = main([str(tmp_path / "does-not-exist.pdf")])
    captured = capsys.readouterr()
    assert rc == 2
    assert "error" in captured.err.lower()


def test_cli_prints_to_stdout_when_no_output(tiny_pdf: Path, capsys):
    rc = main([str(tiny_pdf)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "CLI Heading" in captured.out


def test_cli_with_title_flag_emits_metadata_title(tmp_path: Path):
    doc = fitz.open()
    doc.set_metadata({"title": "My Doc Title"})
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(72, 80), "Body only.", fontname="Helvetica", fontsize=11)
    pdf = tmp_path / "titled.pdf"
    doc.save(str(pdf))
    doc.close()

    out = tmp_path / "out.md"
    rc = main([str(pdf), "-o", str(out), "--with-title"])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# My Doc Title")
