from __future__ import annotations

import fitz

from .model import BBox, Block, Doc


def apply_tables(mu: fitz.Document, doc: Doc) -> None:
    for pno in range(mu.page_count):
        page = mu.load_page(pno)
        tf = _safe_find_tables(page)
        if not tf:
            continue
        page_data = doc.pages[pno]
        for tbl in tf:
            try:
                cells = tbl.extract()
            except Exception:  # pylint: disable=broad-exception-caught
                # PyMuPDF's experimental table extractor can raise a variety
                # of internal errors; a failed table should never poison the
                # whole document conversion.
                continue
            if not cells or not any(any((c or "").strip() for c in row) for row in cells):
                continue
            bbox = BBox(tbl.bbox[0], tbl.bbox[1], tbl.bbox[2], tbl.bbox[3])
            table_block = Block(
                kind="table",
                lines=[],
                bbox=bbox,
                table_cells=[[(c or "").strip() for c in row] for row in cells],
            )
            page_data.blocks = _replace_blocks_inside(page_data.blocks, bbox, table_block)


def _safe_find_tables(page: fitz.Page):
    finder = page.find_tables()
    return getattr(finder, "tables", None) or []


def _replace_blocks_inside(blocks: list[Block], bbox: BBox, new_block: Block) -> list[Block]:
    out: list[Block] = []
    inserted = False
    for b in blocks:
        if b.bbox is not None and _is_inside(b.bbox, bbox):
            if not inserted:
                out.append(new_block)
                inserted = True
            continue
        out.append(b)
    if not inserted:
        out.append(new_block)
        out.sort(key=lambda bl: (bl.bbox.y0 if bl.bbox else 0.0))
    return out


def _is_inside(inner: BBox, outer: BBox, tol: float = 2.0) -> bool:
    return (
        inner.x0 >= outer.x0 - tol
        and inner.y0 >= outer.y0 - tol
        and inner.x1 <= outer.x1 + tol
        and inner.y1 <= outer.y1 + tol
    )
