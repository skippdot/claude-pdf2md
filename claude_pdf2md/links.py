from __future__ import annotations

from .model import BBox, LinkAnnot


def tag_chars_with_urls(chars: list[dict], links: list[LinkAnnot]) -> None:
    if not links:
        for ch in chars:
            ch["url"] = None
        return
    for ch in chars:
        x0, y0, x1, y1 = ch["bbox"]
        ch_bbox = BBox(x0, y0, x1, y1)
        ch["url"] = _uri_for(ch_bbox, links)


def _uri_for(ch: BBox, links: list[LinkAnnot]) -> str | None:
    # PDF link annots are rectangles drawn over the glyph run. A glyph is
    # "on" the link when most of its area falls inside the rect. 0.5 avoids
    # false-positives from link rects that extend slightly past the glyph
    # and false-negatives when the rect sits tight over the baseline.
    # Some Type3 glyphs (e.g. the char 'i' in Chrome-rendered PDFs) arrive
    # with a degenerate zero-width bbox; we fall back to a center-point
    # containment test so those glyphs don't lose their URL.
    area = ch.width * ch.height
    if area <= 0:
        for link in links:
            lb = link.bbox
            if lb.x0 <= ch.cx <= lb.x1 and lb.y0 <= ch.cy <= lb.y1:
                return link.uri
        return None
    best_ratio = -1.0
    best_uri: str | None = None
    for link in links:
        inter = ch.intersect(link.bbox)
        if inter <= 0:
            continue
        ratio = inter / area
        if ratio < 0.5:
            continue
        if ratio > best_ratio:
            best_ratio = ratio
            best_uri = link.uri
    return best_uri
