"""End-to-end roundtrip fidelity tests.

For each case we:
  1. Start with a known Markdown string.
  2. Render MD → PDF via the project's own WeasyPrint pipeline.
  3. Convert that PDF → MD via the public `convert_to_string()` API.
  4. Assert the important invariants survived the trip.

We don't demand byte-exact equality (the PDF render layer reflows
paragraphs and normalises whitespace). We demand preservation of the
content dimensions that matter for downstream consumers: link URLs,
heading levels, list structure, table rows, bold runs, and — modulo
whitespace collapsing — the textual content itself.
"""

from __future__ import annotations

import re

import pytest

from claude_pdf2md import convert_to_string

pytestmark = pytest.mark.roundtrip


def _extract_links(md: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(md):
        m = re.search(r"\[([^\]]*)\]\(", md[i:])
        if not m:
            break
        text = m.group(1)
        start = i + m.end()
        depth = 1
        j = start
        while j < len(md) and depth > 0:
            if md[j] == "(":
                depth += 1
            elif md[j] == ")":
                depth -= 1
            j += 1
        if depth == 0:
            out.append((text, md[start : j - 1]))
        i = j
    return out


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text, flags=re.UNICODE)


# ---------------------------------------------------------------------------
# Link preservation
# ---------------------------------------------------------------------------


def test_roundtrip_preserves_all_link_urls(md_to_pdf):
    source = """# Roundtrip: Link Preservation

This paragraph has a [primary source](https://example.com/one) and a
second [follow-up reference](https://example.org/two?q=1&r=2) mixed
into prose so that neither sits at a line boundary.

- [Bulleted item link](https://example.net/three)
- Plain bullet with no link
- [Trailing item](https://example.com/four#anchor)
"""
    pdf = md_to_pdf(source)
    md = convert_to_string(pdf)

    original_urls = {url for _, url in _extract_links(source)}
    returned_urls = {url for _, url in _extract_links(md)}

    assert original_urls <= returned_urls, f"URLs lost in roundtrip: {original_urls - returned_urls}"


def test_roundtrip_preserves_link_text_for_each_url(md_to_pdf):
    source = (
        "See [Anthropic](https://www.anthropic.com) and "
        "[GitHub repository](https://github.com/anthropics/claude-code).\n"
    )
    pdf = md_to_pdf(source)
    md = convert_to_string(pdf)

    returned = {url: text for text, url in _extract_links(md)}
    assert "Anthropic" in returned.get("https://www.anthropic.com", "")
    assert "GitHub" in returned.get("https://github.com/anthropics/claude-code", "")


def test_roundtrip_preserves_url_with_balanced_parens(md_to_pdf):
    # CommonMark allows balanced parens inside link destinations; our emitter
    # has to reproduce them or the downstream reader loses the URL suffix.
    url = "https://en.wikipedia.org/wiki/Elections_(2026)"
    source = f"Reference: [See wiki]({url}).\n"
    pdf = md_to_pdf(source)
    md = convert_to_string(pdf)

    returned_urls = {u for _, u in _extract_links(md)}
    assert url in returned_urls


# ---------------------------------------------------------------------------
# Heading levels
# ---------------------------------------------------------------------------


def test_roundtrip_preserves_heading_hierarchy(md_to_pdf):
    source = """# Top Level Heading

Intro paragraph under H1.

## Section Two

Body of section two with enough text to occupy a full line of prose.

### Subsection Three

Final subsection body paragraph.
"""
    pdf = md_to_pdf(source)
    md = convert_to_string(pdf)

    lines = [ln.rstrip() for ln in md.splitlines()]
    h1 = [ln for ln in lines if ln.startswith("# ") and not ln.startswith("## ")]
    h2 = [ln for ln in lines if ln.startswith("## ") and not ln.startswith("### ")]
    h3 = [ln for ln in lines if ln.startswith("### ")]

    assert any("Top Level Heading" in h for h in h1)
    assert any("Section Two" in h for h in h2)
    assert any("Subsection Three" in h for h in h3)


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def test_roundtrip_preserves_bullet_list_items(md_to_pdf):
    source = """# List Roundtrip

- First bullet item about alpha
- Second bullet item about beta
- Third bullet item about gamma
"""
    pdf = md_to_pdf(source)
    md = convert_to_string(pdf)

    for expected in ("alpha", "beta", "gamma"):
        assert expected in md
    bullet_lines = [ln for ln in md.splitlines() if ln.lstrip().startswith(("-", "•"))]
    assert len(bullet_lines) >= 3, f"expected ≥3 bullet lines, got {bullet_lines}"


def test_roundtrip_preserves_ordered_list_numbering(md_to_pdf):
    source = """# Ordered List

1. First numbered step
2. Second numbered step
3. Third numbered step
"""
    pdf = md_to_pdf(source)
    md = convert_to_string(pdf)

    numbers_seen = re.findall(r"^\s*(\d+)\.\s", md, flags=re.MULTILINE)
    assert "1" in numbers_seen
    assert "2" in numbers_seen
    assert "3" in numbers_seen
    assert "First numbered step" in _normalize(md)
    assert "Third numbered step" in _normalize(md)


# ---------------------------------------------------------------------------
# Bold
# ---------------------------------------------------------------------------


def test_roundtrip_preserves_bold_runs(md_to_pdf):
    source = (
        "This paragraph includes a **clearly bold phrase** inside otherwise "
        "plain text, and another **second bold run** later on.\n"
    )
    pdf = md_to_pdf(source)
    md = convert_to_string(pdf)

    bold_runs = re.findall(r"\*\*([^*]+)\*\*", md)
    joined = " ".join(bold_runs)
    assert "clearly bold phrase" in joined
    assert "second bold run" in joined


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def test_roundtrip_preserves_markdown_table(md_to_pdf):
    source = """# Table Roundtrip

Intro before the table.

| Party | Percent | Seats |
| --- | --- | --- |
| Alpha | 44.7% | 129 |
| Beta | 13.4% | 39 |
| Gamma | 6.2% | 23 |

Closing paragraph after the table.
"""
    pdf = md_to_pdf(source)
    md = convert_to_string(pdf)

    table_lines = [ln for ln in md.splitlines() if ln.strip().startswith("|")]
    assert any(
        "Party" in ln and "Percent" in ln and "Seats" in ln for ln in table_lines
    ), f"header row missing from roundtripped table: {table_lines}"
    joined = "\n".join(table_lines)
    for party in ("Alpha", "Beta", "Gamma"):
        assert party in joined
    for pct in ("44.7%", "13.4%", "6.2%"):
        assert pct in joined


# ---------------------------------------------------------------------------
# Content preservation (prose words survive the trip)
# ---------------------------------------------------------------------------


def test_roundtrip_preserves_prose_wordset(md_to_pdf):
    source = """# Prose Fidelity

The quick brown fox jumps over the lazy dog near the riverbank.
Sphinx of black quartz, judge my vow: pack my box with five dozen
liquor jugs for the journey ahead. Zephyrs blow, vexing daft Jim.
"""
    pdf = md_to_pdf(source)
    md = convert_to_string(pdf)

    original_words = set(_words(source.lower()))
    returned_words = set(_words(md.lower()))
    missing = original_words - returned_words
    # Soft-hyphen joining and font substitution can occasionally drop a
    # short glue word; require that ≥98% of the unique word set survives.
    loss = len(missing) / max(1, len(original_words))
    assert loss < 0.02, f"word loss ratio {loss:.3f}, missing={missing}"


# ---------------------------------------------------------------------------
# Composite: everything together
# ---------------------------------------------------------------------------


_COMPOSITE_MD = """# Composite Roundtrip

Opening paragraph with a [named link](https://example.com/alpha) and a
second [inline citation](https://example.org/beta?x=1) mid-sentence.

## Findings

- First bullet references [another source](https://example.net/gamma).
- Second bullet has a **bold emphasis** inside.
- Third bullet is plain text only.

### Data

| Metric | Value | Change |
| --- | --- | --- |
| Revenue | 44.7 | up |
| Cost | 13.4 | flat |
| Margin | 6.2 | down |

Closing paragraph with **bold tail** and one final
[trailing link](https://example.com/delta).
"""


def test_roundtrip_composite_preserves_every_dimension(md_to_pdf):
    pdf = md_to_pdf(_COMPOSITE_MD)
    md = convert_to_string(pdf)

    # 1. All four URLs survive.
    original_urls = {url for _, url in _extract_links(_COMPOSITE_MD)}
    returned_urls = {url for _, url in _extract_links(md)}
    assert original_urls <= returned_urls, f"lost: {original_urls - returned_urls}"

    # 2. Headings at H1/H2/H3 all present.
    assert re.search(r"^#\s+Composite Roundtrip\b", md, flags=re.MULTILINE)
    assert re.search(r"^##\s+Findings\b", md, flags=re.MULTILINE)
    assert re.search(r"^###\s+Data\b", md, flags=re.MULTILINE)

    # 3. Bulleted list kept three items.
    bullet_lines = [ln for ln in md.splitlines() if ln.lstrip().startswith(("-", "•"))]
    assert len(bullet_lines) >= 3

    # 4. Table rows survive.
    table_lines = [ln for ln in md.splitlines() if ln.strip().startswith("|")]
    joined_tbl = "\n".join(table_lines)
    for metric in ("Revenue", "Cost", "Margin"):
        assert metric in joined_tbl
    for value in ("44.7", "13.4", "6.2"):
        assert value in joined_tbl

    # 5. Bold runs preserved.
    bold_joined = " ".join(re.findall(r"\*\*([^*]+)\*\*", md))
    assert "bold emphasis" in bold_joined
    assert "bold tail" in bold_joined
