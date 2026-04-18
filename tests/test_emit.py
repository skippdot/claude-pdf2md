from __future__ import annotations

from claude_pdf2md.emit import _render_table, _merge_adjacent_bold


def test_render_table_emits_markdown_grid():
    cells = [["Name", "Count"], ["apples", "3"], ["pears", "5"]]
    md = _render_table(cells)
    assert md.splitlines() == [
        "| Name | Count |",
        "| --- | --- |",
        "| apples | 3 |",
        "| pears | 5 |",
    ]


def test_render_table_escapes_pipes_and_newlines():
    cells = [["a|b", "c\nd"]]
    md = _render_table(cells)
    assert "a\\|b" in md
    assert "\n" not in md.replace("\n|", "").replace("| ", "")


def test_merge_adjacent_bold_joins_bold_tokens_around_whitespace():
    tokens = [
        ("new", None, True, False),
        (" ", None, False, False),
        ("investigations", None, True, False),
    ]
    merged = _merge_adjacent_bold(tokens)
    assert len(merged) == 1
    text, url, bold, _italic = merged[0]
    assert text == "new investigations"
    assert bold is True
    assert url is None


def test_merge_adjacent_bold_does_not_cross_non_whitespace():
    tokens = [
        ("foo", None, True, False),
        (" bar ", None, False, False),
        ("baz", None, True, False),
    ]
    merged = _merge_adjacent_bold(tokens)
    assert len(merged) == 3
