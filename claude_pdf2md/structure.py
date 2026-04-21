from __future__ import annotations

import re
from collections import Counter
from itertools import pairwise

from .model import BBox, Block, Doc, Line, Span

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
        page.blocks = _reassemble_list_columns(page.blocks)
    for page in doc.pages:
        for block in page.blocks:
            _classify_block(block, doc.heading_sizes)
    for page in doc.pages:
        page.blocks = _absorb_citation_pills(page.blocks, doc.body_size)
        page.blocks = _detect_visual_tables(page.blocks)
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


_MARKER_LINE_RE = re.compile(r"^\s*([\u2022\u25E6\u25AA\u25CF\u2023\u2043\u204C\u204D\u00B7\-\–\*]|\d{1,3}[\.\)])\s*$")


def _reassemble_list_columns(blocks: list[Block]) -> list[Block]:
    # HTML→PDF renderers (WeasyPrint, Chrome headless, etc.) put bullet or
    # number markers in a narrow left column — a separate text block from
    # the list-item text column. Pair them up by y-alignment, prepend the
    # marker into each text line, and explode the merged block into one
    # block per list item so later classification promotes them.
    if not any(_is_marker_column(b) for b in blocks):
        return blocks
    pairs: dict[int, int] = {}  # marker_idx -> text_idx
    consumed: set[int] = set()
    for i, block in enumerate(blocks):
        if not _is_marker_column(block):
            continue
        partner = _find_marker_partner(blocks, i, consumed)
        if partner is None:
            continue
        pairs[i] = partner
        consumed.add(partner)
    if not pairs:
        return blocks
    text_to_marker = {t: m for m, t in pairs.items()}
    out: list[Block] = []
    skip: set[int] = set(pairs.keys())
    for i, block in enumerate(blocks):
        if i in skip:
            continue
        if i in text_to_marker:
            marker_idx = text_to_marker[i]
            out.extend(_zip_marker_and_text(blocks[marker_idx], block))
        else:
            out.append(block)
    return out


def _is_marker_column(block: Block) -> bool:
    if block.kind in ("heading", "table", "image"):
        return False
    if not block.lines or not block.bbox:
        return False
    if block.bbox.width > 25.0:
        return False
    for line in block.lines:
        if not _MARKER_LINE_RE.match(line.text):
            return False
    return True


def _find_marker_partner(blocks: list[Block], marker_idx: int, used: set[int]) -> int | None:
    marker = blocks[marker_idx]
    for j, cand in enumerate(blocks):
        if j == marker_idx or j in used:
            continue
        if cand.kind in ("heading", "table", "image"):
            continue
        if cand.bbox is None or not cand.lines:
            continue
        if cand.bbox.x0 < marker.bbox.x0:
            continue
        if len(cand.lines) != len(marker.lines):
            continue
        aligned = True
        for ml, cl in zip(marker.lines, cand.lines, strict=True):
            if abs(ml.bbox.y0 - cl.bbox.y0) > 2.0:
                aligned = False
                break
        if aligned:
            return j
    return None


def _zip_marker_and_text(marker_block: Block, text_block: Block) -> list[Block]:
    out: list[Block] = []
    for m_line, t_line in zip(marker_block.lines, text_block.lines, strict=True):
        marker_text = m_line.text.strip()
        if not marker_text:
            continue
        ref = t_line.spans[0] if t_line.spans else None
        marker_span = Span(
            text=f"{marker_text} ",
            bbox=BBox(
                m_line.bbox.x0,
                m_line.bbox.y0,
                m_line.bbox.x1,
                m_line.bbox.y1,
            ),
            size=ref.size if ref else 11.0,
            font=ref.font if ref else "",
            flags=0,
            color=ref.color if ref else 0,
            url=None,
        )
        new_line = Line(
            spans=[marker_span, *t_line.spans],
            bbox=BBox(
                m_line.bbox.x0,
                t_line.bbox.y0,
                t_line.bbox.x1,
                t_line.bbox.y1,
            ),
        )
        out.append(
            Block(
                kind="paragraph",
                lines=[new_line],
                bbox=BBox(
                    m_line.bbox.x0,
                    t_line.bbox.y0,
                    t_line.bbox.x1,
                    t_line.bbox.y1,
                ),
            )
        )
    return out


def _detect_visual_tables(blocks: list[Block]) -> list[Block]:
    # PyMuPDF's text-block splitter puts borderless column-aligned rows back
    # together as a single block whose "lines" are the individual cells —
    # every "line" sits on the same visual y but at distinct x positions.
    # Consecutive row-blocks with matching column counts form a table.
    row_flags = [_is_row_block(b) for b in blocks]
    out: list[Block] = []
    i = 0
    while i < len(blocks):
        if not row_flags[i]:
            out.append(blocks[i])
            i += 1
            continue
        j = i + 1
        while j < len(blocks) and row_flags[j] and _cells_of(blocks[j]) == _cells_of(blocks[i]):
            j += 1
        run = blocks[i:j]
        if j - i >= 2:
            out.append(_rows_to_table(run))
        else:
            out.extend(run)
        i = j
    return out


def _is_row_block(block: Block) -> bool:
    # A table row shows up as a block whose lines are packed on roughly the
    # same y but spread across x. At least 2 "lines" (cells) and the vertical
    # span must stay inside one line height.
    if block.kind in ("heading", "table", "image"):
        return False
    if len(block.lines) < 2 or block.bbox is None:
        return False
    heights = [ln.bbox.y1 - ln.bbox.y0 for ln in block.lines if ln.bbox]
    if not heights:
        return False
    avg_h = sum(heights) / len(heights)
    span_y = block.bbox.y1 - block.bbox.y0
    if span_y > avg_h * 1.6:
        return False
    xs = sorted((ln.bbox.x0, ln.bbox.x1) for ln in block.lines)
    for (_, x1a), (x0b, _) in pairwise(xs):
        if x0b < x1a - 1:
            return False
    return True


def _cells_of(block: Block) -> int:
    return len(block.lines)


def _rows_to_table(rows: list[Block]) -> Block:
    sorted_rows = [sorted(r.lines, key=lambda ln: ln.bbox.x0) for r in rows]
    cells = [[ln.text.strip() for ln in r] for r in sorted_rows]
    x0 = min(r.bbox.x0 for r in rows if r.bbox)
    y0 = min(r.bbox.y0 for r in rows if r.bbox)
    x1 = max(r.bbox.x1 for r in rows if r.bbox)
    y1 = max(r.bbox.y1 for r in rows if r.bbox)
    return Block(kind="table", lines=[], bbox=BBox(x0, y0, x1, y1), table_cells=cells)


def _absorb_citation_pills(blocks: list[Block], body_size: float) -> list[Block]:
    threshold = body_size * _PILL_SIZE_RATIO
    pills: list[Block] = []
    non_pills: list[Block] = []
    for block in blocks:
        if _is_pill_cluster(block, threshold):
            pills.extend(_split_pill_cluster(block))
        else:
            non_pills.append(block)
    if not pills:
        return blocks
    for pill in pills:
        host = _find_pill_host(non_pills, pill)
        if host is None:
            non_pills.append(pill)
            continue
        if _host_already_has_pill_url(host, pill):
            continue
        _insert_pill_into_host(host, pill)
    return non_pills


def _is_pill_cluster(block: Block, size_threshold: float) -> bool:
    # PyMuPDF sometimes groups several horizontally- or vertically-adjacent
    # pill annotations into one block. Every line in such a cluster is an
    # individual pill; accept the block when *all* lines pass the pill test.
    if block.kind in ("heading", "table", "image"):
        return False
    if not block.lines or not block.bbox:
        return False
    for line in block.lines:
        if not _is_pill_line(line, size_threshold):
            return False
    return True


def _split_pill_cluster(block: Block) -> list[Block]:
    if len(block.lines) == 1:
        return [block]
    out: list[Block] = []
    for line in block.lines:
        out.append(Block(kind="paragraph", lines=[line], bbox=line.bbox))
    return out


def _is_pill_line(line: Line, size_threshold: float) -> bool:
    spans = line.spans
    if not spans:
        return False
    if not all(s.url for s in spans if s.text.strip()):
        return False
    for s in spans:
        if s.text.strip() and s.size >= size_threshold:
            return False
    return True


def _find_pill_host(candidates: list[Block], pill: Block) -> Block | None:
    if not pill.bbox:
        return candidates[-1] if candidates else None
    pill_cy = pill.bbox.cy
    containing: list[Block] = []
    for block in candidates:
        if not _can_host_pill(block) or block.bbox is None:
            continue
        if block.bbox.y0 - 1 <= pill_cy <= block.bbox.y1 + 1:
            containing.append(block)
    if containing:
        # Prefer the host whose x-range covers the pill, then the narrowest.
        def score(b: Block) -> tuple[int, float]:
            covers_x = int(b.bbox.x0 <= pill.bbox.x0 and pill.bbox.x1 <= b.bbox.x1)
            return (-covers_x, b.bbox.width)

        containing.sort(key=score)
        return containing[0]
    # Pill sits above or below all hostable blocks: fall back to the closest
    # hostable block above the pill (matches Claude's footnote-pill layout).
    above = [b for b in candidates if _can_host_pill(b) and b.bbox is not None and b.bbox.y1 <= pill.bbox.y0]
    if above:
        return above[-1]
    return next((b for b in reversed(candidates) if _can_host_pill(b)), None)


def _host_already_has_pill_url(host: Block, pill: Block) -> bool:
    pill_urls = {s.url for s in pill.lines[0].spans if s.url}
    if not pill_urls:
        return False
    for line in host.lines:
        for span in line.spans:
            if span.url and span.url in pill_urls:
                return True
    return False


def _insert_pill_into_host(host: Block, pill: Block) -> None:
    pill_spans = list(pill.lines[0].spans)
    if not pill_spans:
        return
    line_idx = _closest_line_idx(host, pill.bbox)
    target_line = host.lines[line_idx]
    insert_at = _insert_position(target_line, pill.bbox)

    tail_like = pill_spans[-1]
    spacer = Span(
        text=" ",
        bbox=tail_like.bbox,
        size=tail_like.size,
        font=tail_like.font,
        flags=0,
        color=tail_like.color,
        url=None,
    )

    chunk: list[Span] = []
    left = target_line.spans[insert_at - 1] if insert_at > 0 else None
    right = target_line.spans[insert_at] if insert_at < len(target_line.spans) else None

    if left is not None and not left.text.endswith((" ", "\t")) and not pill_spans[0].text.startswith(" "):
        chunk.append(spacer)
    chunk.extend(pill_spans)
    if right is not None and not right.text.startswith((" ", "\t")) and not pill_spans[-1].text.endswith(" "):
        chunk.append(
            Span(
                text=" ",
                bbox=tail_like.bbox,
                size=tail_like.size,
                font=tail_like.font,
                flags=0,
                color=tail_like.color,
                url=None,
            )
        )

    target_line.spans[insert_at:insert_at] = chunk

    x0 = min(target_line.bbox.x0, pill.bbox.x0 if pill.bbox else target_line.bbox.x0)
    x1 = max(target_line.bbox.x1, pill.bbox.x1 if pill.bbox else target_line.bbox.x1)
    target_line.bbox = BBox(x0, target_line.bbox.y0, x1, target_line.bbox.y1)
    if host.bbox and pill.bbox:
        host.bbox = BBox(
            min(host.bbox.x0, pill.bbox.x0),
            min(host.bbox.y0, pill.bbox.y0),
            max(host.bbox.x1, pill.bbox.x1),
            max(host.bbox.y1, pill.bbox.y1),
        )


def _closest_line_idx(host: Block, pill_bbox: BBox | None) -> int:
    if pill_bbox is None or not host.lines:
        return len(host.lines) - 1
    pill_cy = pill_bbox.cy
    best = -1
    best_dy = float("inf")
    for i, line in enumerate(host.lines):
        if line.bbox.y0 - 1 <= pill_cy <= line.bbox.y1 + 1:
            return i
        dy = min(abs(pill_cy - line.bbox.y0), abs(pill_cy - line.bbox.y1))
        if dy < best_dy:
            best_dy = dy
            best = i
    return best if best >= 0 else len(host.lines) - 1


def _insert_position(line: Line, pill_bbox: BBox | None) -> int:
    if pill_bbox is None:
        return len(line.spans)
    for i, span in enumerate(line.spans):
        if span.bbox.x0 >= pill_bbox.x0:
            return i
    return len(line.spans)


def _can_host_pill(block: Block) -> bool:
    return block.kind in ("paragraph", "list_item", "ordered_item") and bool(block.lines)


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
    if _is_bold_label(cur) or _is_bold_label(prev):
        # Fully-bold single-line blocks like "Ключевые вопросы:" are inline
        # subheaders the author set apart — merging them into (or out of) a
        # neighbouring paragraph destroys that visual break.
        return False
    return True


_LABEL_PUNCT = set(":.,;?!()[]\u00ab\u00bb\u2014\u2013-\u2022")


def _is_bold_label(block: Block) -> bool:
    if len(block.lines) != 1:
        return False
    line = block.lines[0]
    bold_word_chars = 0
    total_word_chars = 0
    for span in line.spans:
        stripped = span.text.strip()
        if not stripped:
            continue
        # Trailing colons/dashes frequently render in a regular weight even
        # when the adjacent word is bold — strip punctuation-only spans so
        # they don't veto the bold-label classification.
        if all(ch in _LABEL_PUNCT or ch.isspace() for ch in stripped):
            continue
        word_chars = sum(1 for c in stripped if not c.isspace() and c not in _LABEL_PUNCT)
        total_word_chars += word_chars
        if span.bold:
            bold_word_chars += word_chars
    if total_word_chars == 0:
        return False
    return bold_word_chars / total_word_chars >= 0.8


def _extend_block(host: Block, extra: Block) -> None:
    host.lines.extend(extra.lines)
    if host.bbox and extra.bbox:
        host.bbox = BBox(
            min(host.bbox.x0, extra.bbox.x0),
            min(host.bbox.y0, extra.bbox.y0),
            max(host.bbox.x1, extra.bbox.x1),
            max(host.bbox.y1, extra.bbox.y1),
        )
