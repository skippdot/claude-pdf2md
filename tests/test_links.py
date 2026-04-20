from __future__ import annotations

import re

import fitz

from claude_pdf2md import convert_to_string


def _build_pdf(path, sequence, page_size=(595, 842)):
    doc = fitz.open()
    page = doc.new_page(width=page_size[0], height=page_size[1])
    links = []
    for run in sequence:
        text = run["text"]
        x = run["x"]
        y = run["y"]
        size = run.get("size", 12)
        font = run.get("font", "Helvetica")
        page.insert_text(fitz.Point(x, y), text, fontname=font, fontsize=size)
        if "uri" in run:
            width = fitz.get_text_length(text, fontname=font, fontsize=size)
            rect = fitz.Rect(x, y - size + 1, x + width, y + 2)
            links.append((rect, run["uri"]))
            page.insert_link({"kind": fitz.LINK_URI, "from": rect, "uri": run["uri"]})
    doc.save(str(path))
    doc.close()
    return path


def test_link_text_wraps_exact_phrase(tmp_path):
    pdf = _build_pdf(
        tmp_path / "t.pdf",
        [
            {"text": "See the report ", "x": 72, "y": 120},
            {
                "text": "here",
                "x": 72 + fitz.get_text_length("See the report ", fontname="Helvetica", fontsize=12),
                "y": 120,
                "uri": "https://example.com/report",
            },
            {
                "text": " for details.",
                "x": 72 + fitz.get_text_length("See the report here", fontname="Helvetica", fontsize=12),
                "y": 120,
            },
        ],
    )
    md = convert_to_string(pdf, include_title=False)
    assert "[here](https://example.com/report)" in md
    assert "See the report" in md
    assert "for details" in md


def test_multiple_links_preserved(tmp_path):
    x0 = 72
    sequence = []
    cursor = x0
    for label, uri in [
        ("Alpha", "https://a.example"),
        (" and ", None),
        ("Beta", "https://b.example"),
        (" and ", None),
        ("Gamma", "https://g.example"),
        (".", None),
    ]:
        run = {"text": label, "x": cursor, "y": 120}
        if uri:
            run["uri"] = uri
        sequence.append(run)
        cursor += fitz.get_text_length(label, fontname="Helvetica", fontsize=12)
    pdf = _build_pdf(tmp_path / "t.pdf", sequence)
    md = convert_to_string(pdf, include_title=False)
    assert "[Alpha](https://a.example)" in md
    assert "[Beta](https://b.example)" in md
    assert "[Gamma](https://g.example)" in md


def test_no_spurious_links(tmp_path):
    pdf = _build_pdf(
        tmp_path / "t.pdf",
        [{"text": "Plain paragraph with no links.", "x": 72, "y": 120}],
    )
    md = convert_to_string(pdf, include_title=False)
    assert re.search(r"\]\([^)]+\)", md) is None


def test_url_recall_on_bulgaria_watch(bulgaria_watch_pdf):
    md = convert_to_string(bulgaria_watch_pdf)
    doc = fitz.open(bulgaria_watch_pdf)
    pdf_urls = {link["uri"] for page in doc for link in page.get_links() if link.get("uri")}
    doc.close()
    md_urls = set(re.findall(r"\]\(([^)]+)\)", md))
    missing = pdf_urls - md_urls
    assert not missing, f"Missing {len(missing)} URIs: {list(missing)[:3]}"
