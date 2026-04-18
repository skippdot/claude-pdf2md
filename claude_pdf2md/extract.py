from __future__ import annotations

import fitz

from .links import tag_chars_with_urls
from .model import BBox, Block, Doc, ImageAnnot, Line, LinkAnnot, Page, Span


def extract_doc(pdf_path: str) -> tuple[fitz.Document, Doc]:
    mu = fitz.open(pdf_path)
    title = (mu.metadata or {}).get("title") or ""
    doc = Doc(title=title)
    for pno in range(mu.page_count):
        doc.pages.append(_extract_page(mu.load_page(pno), pno))
    return mu, doc


def _extract_page(page: fitz.Page, pno: int) -> Page:
    rect = page.rect
    p = Page(number=pno, width=rect.width, height=rect.height)

    for link in page.get_links():
        uri = link.get("uri")
        if not uri:
            continue
        r = link["from"]
        p.links.append(LinkAnnot(bbox=_bbox(r), uri=uri))

    raw = page.get_text("rawdict")
    for block in raw.get("blocks", []):
        btype = block.get("type")
        bbox = _bbox(block["bbox"])
        if btype == 1:
            p.images.append(
                ImageAnnot(
                    xref=block.get("xref", 0),
                    bbox=bbox,
                    ext=block.get("ext", "png"),
                    data=block.get("image", b""),
                )
            )
            continue
        if btype != 0:
            continue
        lines = _lines_from_raw_block(block, p.links)
        if lines:
            p.blocks.append(Block(kind="paragraph", lines=lines, bbox=bbox))

    return p


def _lines_from_raw_block(block: dict, links: list[LinkAnnot]) -> list[Line]:
    out: list[Line] = []
    for raw_line in block.get("lines", []):
        chars = _chars_from_raw_line(raw_line)
        if not chars:
            continue
        tag_chars_with_urls(chars, links)
        spans = _merge_chars_to_spans(chars)
        if not spans:
            continue
        x0 = min(s.bbox.x0 for s in spans)
        y0 = min(s.bbox.y0 for s in spans)
        x1 = max(s.bbox.x1 for s in spans)
        y1 = max(s.bbox.y1 for s in spans)
        out.append(Line(spans=spans, bbox=BBox(x0, y0, x1, y1)))
    return out


def _chars_from_raw_line(raw_line: dict) -> list[dict]:
    chars: list[dict] = []
    for span in raw_line.get("spans", []):
        font = span.get("font", "")
        size = float(span.get("size", 0.0))
        flags = int(span.get("flags", 0))
        color = int(span.get("color", 0))
        for ch in span.get("chars", []):
            c = ch.get("c", "")
            if not c:
                continue
            bbox = ch.get("bbox")
            if not bbox:
                continue
            chars.append(
                {
                    "c": c,
                    "bbox": bbox,
                    "font": font,
                    "size": size,
                    "flags": flags,
                    "color": color,
                }
            )
    # Don't re-sort: PyMuPDF already hands chars back in PDF stream (reading)
    # order; glyphs of different ascender height within the same line would
    # otherwise be split into separate y-buckets and scrambled.
    return chars


def _merge_chars_to_spans(chars: list[dict]) -> list[Span]:
    spans: list[Span] = []
    if not chars:
        return spans

    def _same_style(a: dict, b: dict) -> bool:
        return (
            a["font"] == b["font"]
            and abs(a["size"] - b["size"]) < 0.1
            and a["color"] == b["color"]
            and a["flags"] == b["flags"]
            and a.get("url") == b.get("url")
        )

    def _flush(buf: list[dict]) -> None:
        if not buf:
            return
        text = "".join(ch["c"] for ch in buf)
        x0 = min(ch["bbox"][0] for ch in buf)
        y0 = min(ch["bbox"][1] for ch in buf)
        x1 = max(ch["bbox"][2] for ch in buf)
        y1 = max(ch["bbox"][3] for ch in buf)
        spans.append(
            Span(
                text=text,
                bbox=BBox(x0, y0, x1, y1),
                size=buf[0]["size"],
                font=buf[0]["font"],
                flags=buf[0]["flags"],
                color=buf[0]["color"],
                url=buf[0].get("url"),
            )
        )

    buf: list[dict] = [chars[0]]
    for ch in chars[1:]:
        prev = buf[-1]
        gap = ch["bbox"][0] - prev["bbox"][2]
        max_gap_joined = max(prev["size"], 1.0) * 0.6
        if _same_style(prev, ch) and gap <= max_gap_joined:
            buf.append(ch)
        elif _same_style(prev, ch) and gap <= prev["size"] * 1.2:
            buf.append({**ch, "c": " " + ch["c"]})
        else:
            _flush(buf)
            buf = [ch]
    _flush(buf)
    return spans


def _bbox(r) -> BBox:
    if isinstance(r, fitz.Rect):
        return BBox(r.x0, r.y0, r.x1, r.y1)
    x0, y0, x1, y1 = r
    return BBox(float(x0), float(y0), float(x1), float(y1))
