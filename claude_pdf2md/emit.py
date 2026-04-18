from __future__ import annotations

import re

from .model import Block, Doc, Line, Span
from .structure import strip_list_marker

_SOFT_HYPHEN_RE = re.compile(r"(\w)-\s*$")
_MARKUP_ESCAPE = {ord("["): r"\[", ord("]"): r"\]"}


def render(doc: Doc, include_title: bool = True) -> str:
    out: list[str] = []
    if include_title and doc.title:
        out.append(f"# {doc.title}")
    for page in doc.pages:
        for block in page.blocks:
            chunk = _render_block(block)
            if chunk:
                out.append(chunk)
    return "\n\n".join(out).rstrip() + "\n"


def _render_block(block: Block) -> str:
    if block.kind == "image":
        if not block.image_path:
            return ""
        return f"![{block.image_alt}]({block.image_path})"
    if block.kind == "table":
        return _render_table(block.table_cells or [])

    text = _lines_to_md(block.lines)
    if not text.strip():
        return ""

    if block.kind in ("list_item", "ordered_item"):
        text = strip_list_marker(text).strip()

    if block.kind == "heading":
        level = max(1, min(block.level or 1, 6))
        clean = _strip_inline_bold(text.strip())
        return f"{'#' * level} {clean}"
    if block.kind == "list_item":
        indent = "  " * block.indent_level
        return f"{indent}- {text}"
    if block.kind == "ordered_item":
        indent = "  " * block.indent_level
        n = block.ordered_index or 1
        return f"{indent}{n}. {text}"
    return text.strip()


def _lines_to_md(lines: list[Line]) -> str:
    tokens: list[tuple[str, str | None, bool, bool]] = []
    for idx, line in enumerate(lines):
        if idx > 0 and tokens:
            prev_text = tokens[-1][0]
            prev_url = tokens[-1][1]
            next_url = line.spans[0].url if line.spans else None
            joiner_url = prev_url if prev_url == next_url else None
            if _SOFT_HYPHEN_RE.search(prev_text):
                tokens[-1] = (prev_text[:-1], prev_url, tokens[-1][2], tokens[-1][3])
            else:
                tokens.append((" ", joiner_url, False, False))
        for s in line.spans:
            tokens.append((s.text, s.url, s.bold, s.italic))
    return _tokens_to_md(tokens)


def _tokens_to_md(tokens: list[tuple[str, str | None, bool, bool]]) -> str:
    tokens = _merge_adjacent_bold(tokens)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        url = tokens[i][1]
        if url:
            j = i
            buf = []
            while j < len(tokens) and tokens[j][1] == url:
                buf.append(tokens[j])
                j += 1
            inner = _styled_run(buf)
            inner_text = inner.strip()
            if inner_text:
                safe = inner_text.translate(_MARKUP_ESCAPE)
                leading_ws = inner[: len(inner) - len(inner.lstrip())]
                trailing_ws = inner[len(inner.rstrip()):]
                out.append(f"{leading_ws}[{safe}]({url}){trailing_ws}")
            else:
                out.append(inner)
            i = j
        else:
            out.append(_styled_token(tokens[i]))
            i += 1
    return "".join(out)


def _merge_adjacent_bold(
    tokens: list[tuple[str, str | None, bool, bool]],
) -> list[tuple[str, str | None, bool, bool]]:
    # "**в** **год**" reads worse than "**в год**". When two bold tokens sit
    # with only whitespace between them (same url, same italic), absorb the
    # whitespace into the first so the downstream renderer sees one run.
    out = list(tokens)
    i = 0
    while i + 2 < len(out):
        a, mid, c = out[i], out[i + 1], out[i + 2]
        if (
            a[2]
            and c[2]
            and not mid[2]
            and a[1] == mid[1] == c[1]
            and a[3] == c[3]
            and mid[0].strip() == ""
        ):
            out[i] = (a[0] + mid[0] + c[0], a[1], True, a[3])
            del out[i + 1 : i + 3]
            continue
        i += 1
    return out


def _styled_run(tokens: list[tuple[str, str | None, bool, bool]]) -> str:
    return "".join(_styled_token(t) for t in tokens)


def _styled_token(tok: tuple[str, str | None, bool, bool]) -> str:
    text, _url, bold, _italic = tok
    if not text or not text.strip():
        return text
    if bold:
        stripped = text.strip()
        prefix = text[: len(text) - len(text.lstrip())]
        suffix = text[len(text.rstrip()):]
        return f"{prefix}**{stripped}**{suffix}"
    return text


def _render_table(cells: list[list[str]]) -> str:
    if not cells:
        return ""
    width = max(len(r) for r in cells)
    norm = [list(r) + [""] * (width - len(r)) for r in cells]
    header, *body = norm
    if not any((c or "").strip() for c in header):
        header = [f"col{i + 1}" for i in range(width)]
        body = norm
    header_md = "| " + " | ".join(_cell(c) for c in header) + " |"
    sep_md = "| " + " | ".join(["---"] * width) + " |"
    body_md = "\n".join("| " + " | ".join(_cell(c) for c in row) + " |" for row in body)
    return "\n".join([header_md, sep_md, body_md]).rstrip()


def _cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def _strip_inline_bold(text: str) -> str:
    # Headings look loud with every Georgia-Bold word wrapped in **. The
    # heading itself already conveys emphasis, so flatten nested **...** noise.
    return re.sub(r"\*\*(.*?)\*\*", r"\1", text)
