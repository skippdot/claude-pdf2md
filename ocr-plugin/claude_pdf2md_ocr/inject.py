"""Turn OCR words into `claude_pdf2md.model` Blocks/Lines/Spans.

`structure.analyze_document` downstream expects blocks with lines whose bboxes
are consistent — y0/y1 bounded by the line's word extrema, x0/x1 spanning the
leftmost to rightmost word. Font size is approximated as the bbox height
(good enough; the structure module only uses it to discriminate body vs.
heading tiers and OCR pages rarely have reliable font metrics anyway)."""

from __future__ import annotations

from claude_pdf2md.model import BBox, Block, Line, Span

from .backends import OcrWord


def words_to_blocks(words: list[OcrWord], min_confidence: float = 0.0) -> list[Block]:
    """Group OCR words into Lines (by `line_id`) and one Block per line.

    We emit one paragraph-kind Block per line, letting the existing
    `structure.analyze_document` post-pass merge consecutive lines into
    paragraphs and detect headings by size. Giving the structure pass a list
    of single-line blocks is what the text-layer extractor does too, so the
    downstream behavior is the same.
    """
    by_line: dict[int, list[OcrWord]] = {}
    for w in words:
        if w.confidence < min_confidence:
            continue
        by_line.setdefault(w.line_id, []).append(w)

    blocks: list[Block] = []
    for line_id in sorted(by_line.keys()):
        line_words = sorted(by_line[line_id], key=lambda w: w.x0)
        if not line_words:
            continue
        x0 = min(w.x0 for w in line_words)
        y0 = min(w.y0 for w in line_words)
        x1 = max(w.x1 for w in line_words)
        y1 = max(w.y1 for w in line_words)
        line_bbox = BBox(x0, y0, x1, y1)
        # Build one Span per word so later passes can still reason word-by-word
        # if they need to (e.g. a future per-word confidence filter). Spans
        # carry a trailing space so `Line.text` reassembles naturally via the
        # `"".join(s.text for s in spans)` model rule.
        spans: list[Span] = []
        for idx, w in enumerate(line_words):
            tail = " " if idx < len(line_words) - 1 else ""
            size = w.y1 - w.y0
            spans.append(
                Span(
                    text=w.text + tail,
                    bbox=BBox(w.x0, w.y0, w.x1, w.y1),
                    size=size,
                    font="OCR",
                    flags=0,
                    color=0,
                    url=None,
                )
            )
        line = Line(spans=spans, bbox=line_bbox)
        blocks.append(Block(kind="paragraph", lines=[line], bbox=line_bbox))
    return blocks
