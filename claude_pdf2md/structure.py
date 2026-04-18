from __future__ import annotations

import re
from collections import Counter

from .model import BBox, Block, Doc, Line, Page

_BULLET_PREFIX = re.compile(r"^\s*([\u2022\u25E6\u25AA\u25CF\u2023\u2043\u204C\u204D\u00B7\-\–\*])\s+")
_ORDERED_PREFIX = re.compile(r"^\s*(\d{1,3})[\.\)]\s+")

_HEADING_SIZE_RATIO = 1.10
_MAX_HEADING_LEVELS = 3
_PILL_SIZE_RATIO = 0.90
_CONTINUATION_Y_GAP = 1.8
_CONTINUATION_X_TOL = 14.0


def analyze_document(doc: Doc) -> None:
    doc.body_size = _body_size(doc)
    doc.heading_sizes = _heading_size_buckets(doc, doc.body_size)
    for page in doc.pages:
        for block in page.blocks:
            _classify_block(block, doc.heading_sizes)
    for page in doc.pages:
        page.blocks = _absorb_citation_pills(page.blocks, doc.body_size)
        page.blocks = _merge_wrapped_continuations(page.blocks)


def _body_size(doc: Doc) -> float:
    weights: Counter[float] = Counter()
    for page in doc.pages:
        for block in page.blocks:
            for line in block.lines:
                for span in line.spans:
                    text = span.text.strip()
                    if not text:
                        continue
                    weights[round(span.size, 1)] += len(text)
    if not weights:
        return 10.0
    return weights.most_common(1)[0][0]


def _heading_size_buckets(doc: Doc, body_size: float) -> list[float]:
    sizes: Counter[float] = Counter()
    for page in doc.pages:
        for block in page.blocks:
            first_line = next((ln for ln in block.lines if ln.text.strip()), None)
            if not first_line:
                continue
            s = round(first_line.dominant_size, 1)
            if s >= body_size * _HEADING_SIZE_RATIO:
                sizes[s] += 1
    if not sizes:
        return []
    return sorted(sizes.keys(), reverse=True)[:_MAX_HEADING_LEVELS]


def _classify_block(block: Block, heading_sizes: list[float]) -> None:
    first_line = next((ln for ln in block.lines if ln.text.strip()), None)
    if not first_line:
        return
    line_text = first_line.text.strip()
    line_size = round(first_line.dominant_size, 1)

    if heading_sizes and line_size in heading_sizes:
        block.kind = "heading"
        block.level = heading_sizes.index(line_size) + 1
        return
    if heading_sizes and line_size > heading_sizes[0]:
        block.kind = "heading"
        block.level = 1
        return

    m_ord = _ORDERED_PREFIX.match(line_text)
    if m_ord:
        block.kind = "ordered_item"
        block.ordered_index = int(m_ord.group(1))
        block.indent_level = _indent_level(block)
        return

    if _BULLET_PREFIX.match(line_text):
        block.kind = "list_item"
        block.indent_level = _indent_level(block)
        return

    block.kind = "paragraph"


def _indent_level(block: Block) -> int:
    if not block.bbox:
        return 0
    x0 = block.bbox.x0
    if x0 < 60:
        return 0
    if x0 < 100:
        return 1
    if x0 < 140:
        return 2
    return 3


def strip_list_marker(text: str) -> str:
    text = _BULLET_PREFIX.sub("", text, count=1)
    text = _ORDERED_PREFIX.sub("", text, count=1)
    return text


def _absorb_citation_pills(blocks: list[Block], body_size: float) -> list[Block]:
    threshold = body_size * _PILL_SIZE_RATIO
    out: list[Block] = []
    for block in blocks:
        if _is_citation_pill(block, threshold) and out and _can_host_pill(out[-1]):
            if _host_already_has_pill_url(out[-1], block):
                continue
            _append_pill_to(out[-1], block)
            continue
        out.append(block)
    return out


def _host_already_has_pill_url(host: Block, pill: Block) -> bool:
    pill_urls = {s.url for s in pill.lines[0].spans if s.url}
    if not pill_urls:
        return False
    seen: set[str] = set()
    for line in host.lines:
        for span in line.spans:
            if span.url:
                seen.add(span.url)
    return bool(pill_urls & seen)


def _is_citation_pill(block: Block, size_threshold: float) -> bool:
    if block.kind in ("heading", "table", "image"):
        return False
    if not block.lines or not block.bbox:
        return False
    if len(block.lines) != 1:
        return False
    spans = block.lines[0].spans
    if not spans:
        return False
    if not all(s.url for s in spans if s.text.strip()):
        return False
    for s in spans:
        if s.text.strip() and s.size >= size_threshold:
            return False
    return True


def _can_host_pill(block: Block) -> bool:
    return block.kind in ("paragraph", "list_item", "ordered_item") and bool(block.lines)


def _append_pill_to(host: Block, pill: Block) -> None:
    pill_spans = list(pill.lines[0].spans)
    if not pill_spans:
        return
    last_line = host.lines[-1]
    last_line.spans.extend(_spacer_spans(last_line, pill_spans[0]))
    last_line.spans.extend(pill_spans)
    x1 = max(last_line.bbox.x1, pill.bbox.x1 if pill.bbox else last_line.bbox.x1)
    last_line.bbox = BBox(last_line.bbox.x0, last_line.bbox.y0, x1, last_line.bbox.y1)
    if host.bbox and pill.bbox:
        host.bbox = BBox(
            min(host.bbox.x0, pill.bbox.x0),
            min(host.bbox.y0, pill.bbox.y0),
            max(host.bbox.x1, pill.bbox.x1),
            max(host.bbox.y1, pill.bbox.y1),
        )


def _spacer_spans(host_line: Line, next_span) -> list:
    if not host_line.spans:
        return []
    last_text = host_line.spans[-1].text
    if last_text.endswith((" ", "\t")) or (next_span.text and next_span.text.startswith(" ")):
        return []
    from .model import Span
    tail = host_line.spans[-1]
    return [
        Span(
            text=" ",
            bbox=tail.bbox,
            size=tail.size,
            font=tail.font,
            flags=0,
            color=tail.color,
            url=None,
        )
    ]


def _merge_wrapped_continuations(blocks: list[Block]) -> list[Block]:
    if not blocks:
        return blocks
    out: list[Block] = [blocks[0]]
    for block in blocks[1:]:
        prev = out[-1]
        if _is_continuation_of(prev, block):
            _extend_block(prev, block)
        else:
            out.append(block)
    return out


def _is_continuation_of(prev: Block, cur: Block) -> bool:
    if prev.kind in ("heading", "table", "image"):
        return False
    if cur.kind in ("heading", "table", "image", "list_item", "ordered_item"):
        return False
    if cur.kind != "paragraph":
        return False
    if not prev.bbox or not cur.bbox or not prev.lines or not cur.lines:
        return False
    prev_last_size = prev.lines[-1].dominant_size or prev.lines[-1].spans[0].size
    gap = cur.bbox.y0 - prev.bbox.y1
    if gap > prev_last_size * _CONTINUATION_Y_GAP:
        return False
    if gap < -prev_last_size:
        return False
    if prev.kind in ("list_item", "ordered_item"):
        # List markers shift prev.bbox.x0 left of the content column, so a
        # wrapped continuation line can sit up to ~30pt to the right; widen.
        dx = cur.bbox.x0 - prev.bbox.x0
        if dx < -_CONTINUATION_X_TOL or dx > 40.0:
            return False
    elif abs(cur.bbox.x0 - prev.bbox.x0) > _CONTINUATION_X_TOL:
        return False
    first_text = cur.lines[0].text.strip()
    if not first_text:
        return False
    if _BULLET_PREFIX.match(first_text) or _ORDERED_PREFIX.match(first_text):
        return False
    return True


def _extend_block(host: Block, extra: Block) -> None:
    host.lines.extend(extra.lines)
    if host.bbox and extra.bbox:
        host.bbox = BBox(
            min(host.bbox.x0, extra.bbox.x0),
            min(host.bbox.y0, extra.bbox.y0),
            max(host.bbox.x1, extra.bbox.x1),
            max(host.bbox.y1, extra.bbox.y1),
        )
