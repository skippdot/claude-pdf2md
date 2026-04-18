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
    best: tuple[float, str] | None = None
    for link in links:
        inter = ch.intersect(link.bbox)
        if inter <= 0:
            continue
        area = ch.width * ch.height
        if area <= 0:
            continue
        ratio = inter / area
        if ratio < 0.5:
            continue
        if best is None or ratio > best[0]:
            best = (ratio, link.uri)
    return best[1] if best else None
