from __future__ import annotations

import re

import fitz

from claude_pdf2md import convert_to_string
from claude_pdf2md.model import BBox, Block, Doc, Line, LinkAnnot, Page, Span
from claude_pdf2md.structure import analyze_document
from claude_pdf2md.emit import render


def _span(text, x0, y0, x1, y1, size=12.0, font="Helvetica", bold=False, url=None):
    flags = 16 if bold else 0
    return Span(
        text=text,
        bbox=BBox(x0, y0, x1, y1),
        size=size,
        font=font,
        flags=flags,
        color=0,
        url=url,
    )


def _line_from_spans(spans):
    x0 = min(s.bbox.x0 for s in spans)
    y0 = min(s.bbox.y0 for s in spans)
    x1 = max(s.bbox.x1 for s in spans)
    y1 = max(s.bbox.y1 for s in spans)
    return Line(spans=list(spans), bbox=BBox(x0, y0, x1, y1))


def _block(kind, lines, **kwargs):
    x0 = min(ln.bbox.x0 for ln in lines) if lines else 0.0
    y0 = min(ln.bbox.y0 for ln in lines) if lines else 0.0
    x1 = max(ln.bbox.x1 for ln in lines) if lines else 0.0
    y1 = max(ln.bbox.y1 for ln in lines) if lines else 0.0
    return Block(kind=kind, lines=list(lines), bbox=BBox(x0, y0, x1, y1), **kwargs)


def test_metadata_title_is_not_emitted_by_default(tmp_path):
    doc = fitz.open()
    doc.set_metadata({"title": "Document Metadata Title"})
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(72, 80), "Visible Document Heading", fontname="Helvetica-Bold", fontsize=20)
    page.insert_text(fitz.Point(72, 140), "Body paragraph.", fontname="Helvetica", fontsize=11)
    pdf = tmp_path / "meta.pdf"
    doc.save(str(pdf))
    doc.close()

    md = convert_to_string(pdf)
    assert "Document Metadata Title" not in md
    assert "Visible Document Heading" in md


def test_metadata_title_emitted_when_opted_in(tmp_path):
    doc = fitz.open()
    doc.set_metadata({"title": "Document Metadata Title"})
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(72, 80), "Some body.", fontname="Helvetica", fontsize=11)
    pdf = tmp_path / "meta.pdf"
    doc.save(str(pdf))
    doc.close()

    md = convert_to_string(pdf, include_title=True)
    assert md.startswith("# Document Metadata Title")


def test_citation_pill_inserted_inline_between_words():
    # Real Claude research PDFs hand back pill blocks AFTER every body block
    # on the page, not inline with them. Simulate that layout and prove the
    # pill lands between "Before" and "after", not trailing at the end.
    body_line = _line_from_spans(
        [
            _span("Before ", 72, 110, 110, 125, size=12, url=None),
            _span("after the pill.", 130, 110, 230, 125, size=12, url=None),
        ]
    )
    body = _block("paragraph", [body_line])
    pill_line = _line_from_spans([_span("Source", 115, 114, 129, 123, size=9, url="https://src.example")])
    pill = _block("paragraph", [pill_line])
    page = Page(number=0, width=595, height=842, blocks=[body, pill])
    doc = Doc(pages=[page])

    analyze_document(doc)
    md = render(doc, include_title=False)

    link_idx = md.find("[Source](https://src.example)")
    after_idx = md.find("after the pill.")
    assert link_idx != -1 and after_idx != -1
    assert link_idx < after_idx, f"pill placed wrong: {md!r}"


def test_citation_pill_after_paragraph_tail_preserves_order():
    body_line = _line_from_spans([_span("Paragraph text.", 72, 110, 180, 125)])
    body = _block("paragraph", [body_line])
    pill_line = _line_from_spans([_span("Src", 190, 113, 215, 123, size=9, url="https://x.example")])
    pill = _block("paragraph", [pill_line])
    page = Page(number=0, width=595, height=842, blocks=[body, pill])
    doc = Doc(pages=[page])

    analyze_document(doc)
    md = render(doc, include_title=False)
    assert "Paragraph text." in md
    assert "[Src](https://x.example)" in md
    assert md.index("Paragraph text.") < md.index("[Src](https://x.example)")


def test_bold_label_block_is_emitted_on_its_own_line():
    pre = _block("paragraph", [_line_from_spans([_span("Prior paragraph text.", 72, 110, 260, 125)])])
    label = _block(
        "paragraph",
        [
            _line_from_spans(
                [
                    _span("Key Questions", 72, 145, 160, 160, bold=True),
                    _span(":", 160, 145, 164, 160, bold=False),
                ]
            )
        ],
    )
    post = _block(
        "paragraph",
        [_line_from_spans([_span("First follow-up sentence.", 72, 180, 260, 195)])],
    )
    page = Page(number=0, width=595, height=842, blocks=[pre, label, post])
    doc = Doc(pages=[page])

    analyze_document(doc)
    md = render(doc, include_title=False)

    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
    assert "Prior paragraph text." in lines
    assert "**Key Questions**:" in lines
    assert "First follow-up sentence." in lines


def test_no_double_spaces_around_links_on_bulgaria_watch(bulgaria_watch_pdf):
    md = convert_to_string(bulgaria_watch_pdf)
    doubles = re.findall(r"\S[ ]{2,}\S", md)
    # A handful of double-spaces originate in the source PDF itself (they sit
    # inside span.text). Cap well below the 30+ that the joiner bug used to
    # produce.
    assert len(doubles) < 15, f"too many double-spaces: {len(doubles)}"


def test_bulgaria_watch_does_not_duplicate_title(bulgaria_watch_pdf):
    md = convert_to_string(bulgaria_watch_pdf)
    assert "Bulgaria Watch #40-#49: 10 New Investigations" not in md
    assert "Bulgaria Watch #40–#49: 10 новых расследований" in md


def test_zero_width_glyph_inside_link_still_tags_url():
    # Chrome-rendered PDFs emit the glyph 'i' with a zero-width bbox. When the
    # link rect covers the whole word, the narrow 'i' still belongs to the link.
    from claude_pdf2md.links import _uri_for
    from claude_pdf2md.model import BBox, LinkAnnot

    link_rect = BBox(100.0, 100.0, 200.0, 120.0)
    degenerate_i = BBox(150.0, 105.0, 150.0, 115.0)
    normal_a = BBox(155.0, 105.0, 160.0, 115.0)
    outside = BBox(50.0, 105.0, 50.0, 115.0)
    links = [LinkAnnot(bbox=link_rect, uri="https://example.com")]

    assert _uri_for(degenerate_i, links) == "https://example.com"
    assert _uri_for(normal_a, links) == "https://example.com"
    assert _uri_for(outside, links) is None


def test_multi_line_pill_cluster_is_split_and_absorbed():
    # PyMuPDF sometimes packs three adjacent pills into one "block" whose
    # three lines are the individual pills. Each line has to land inline in
    # the host paragraph, not dangle as a trailing block.
    body_line = _line_from_spans(
        [
            _span("Host paragraph sentence that spans a range.", 50, 100, 350, 115, size=12),
        ]
    )
    body = _block("paragraph", [body_line])

    def pill_line(text, x0, url):
        return _line_from_spans([_span(text, x0, 118, x0 + 40, 128, size=9, url=url)])

    cluster = _block(
        "paragraph",
        [
            pill_line("One", 60, "https://a.example"),
            pill_line("Two", 120, "https://b.example"),
            pill_line("Three", 200, "https://c.example"),
        ],
    )
    page = Page(number=0, width=595, height=842, blocks=[body, cluster])
    doc = Doc(pages=[page])

    analyze_document(doc)
    md = render(doc, include_title=False)

    for url in ("https://a.example", "https://b.example", "https://c.example"):
        assert url in md, f"pill {url} was dropped"
    # And the pills must be inlined (no standalone "[Two](...)\n\n[Three]..." pair).
    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
    standalone_pill_lines = [
        ln for ln in lines if ln.startswith("[") and "Host paragraph" not in ln
    ]
    assert not standalone_pill_lines, f"pills left dangling: {standalone_pill_lines}"


def test_visual_table_rows_are_promoted_to_markdown_table():
    # PyMuPDF returns each borderless table row as a block whose "lines" are
    # the individual cells — all at near-identical y, non-overlapping x.
    def row(label, pct, count, note, y):
        line_a = _line_from_spans([_span(label, 40, y, 180, y + 12)])
        line_b = _line_from_spans([_span(pct, 220, y, 260, y + 12)])
        line_c = _line_from_spans([_span(count, 310, y, 350, y + 12)])
        line_d = _line_from_spans([_span(note, 390, y, 520, y + 12)])
        return _block("paragraph", [line_a, line_b, line_c, line_d])

    body = _block(
        "paragraph",
        [_line_from_spans([_span("Intro paragraph.", 40, 40, 160, 54)])],
    )
    header = row("Party", "%", "Seats", "Change", 70)
    r1 = row("Alpha", "44", "129", "new", 100)
    r2 = row("Beta", "13", "39", "loss", 130)
    page = Page(number=0, width=595, height=842, blocks=[body, header, r1, r2])
    doc = Doc(pages=[page])

    analyze_document(doc)
    md = render(doc, include_title=False)

    assert "| Party | % | Seats | Change |" in md
    assert "| Alpha | 44 | 129 | new |" in md
    assert "| Beta | 13 | 39 | loss |" in md
