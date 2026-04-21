"""Turn OCR words into `claude_pdf2md.model` Blocks/Lines/Spans.

`structure.analyze_document` downstream compares each block's dominant
font size against document-wide body size (mode) and heading-size buckets
(≥ 1.10× body). Naively using per-word bbox height as the span size makes
body text look like a forest of tiny heading tiers, because bbox height
fluctuates with the letters present (descenders / ascenders / caps).

We sidestep that by quantising every OCR word on a page to a single
per-page "body" size — the median of word heights, rounded to the nearest
half-point — while genuinely tall lines (titles at least 1.2× the median)
keep their measured height so real headings still get promoted by the
downstream analyser.
"""

from __future__ import annotations

from statistics import median

from claude_pdf2md.model import BBox, Block, Line, Span

from .backends import OcrWord

_HEADING_RATIO = 1.2  # Keep a word's real size only when it clearly exceeds the page body size.


def words_to_blocks(words: list[OcrWord], min_confidence: float = 0.0) -> list[Block]:
    """Group OCR words into Lines (by `line_id`) and one Block per line."""
    kept = [w for w in words if w.confidence >= min_confidence]
    if not kept:
        return []

    body_size = _page_body_size(kept)

    by_line: dict[int, list[OcrWord]] = {}
    for w in kept:
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
            raw_size = w.y1 - w.y0
            size = raw_size if raw_size >= body_size * _HEADING_RATIO else body_size
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


def _page_body_size(words: list[OcrWord]) -> float:
    """Median word-height for the page, rounded to the nearest 0.5 pt."""
    heights = [w.y1 - w.y0 for w in words if w.y1 > w.y0]
    if not heights:
        return 10.0
    med = median(heights)
    return round(med * 2) / 2
