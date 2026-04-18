from __future__ import annotations

from claude_pdf2md import convert_to_string


def test_headings_detected_by_size(tmp_pdf):
    pdf = tmp_pdf(
        [
            {
                "text": [
                    {"text": "Document Title", "x": 72, "y": 80, "size": 20},
                    {"text": "Section One", "x": 72, "y": 140, "size": 15},
                    {"text": "Body paragraph.", "x": 72, "y": 200, "size": 11},
                ]
            }
        ]
    )
    md = convert_to_string(pdf, include_title=False)
    assert "# Document Title" in md
    assert "## Section One" in md
    assert "Body paragraph." in md


def test_ordered_list_is_detected(tmp_pdf):
    pdf = tmp_pdf(
        [
            {
                "text": [
                    {"text": "1. First item in list.", "x": 72, "y": 120, "size": 11},
                    {"text": "2. Second item.", "x": 72, "y": 160, "size": 11},
                    {"text": "3. Third item.", "x": 72, "y": 200, "size": 11},
                ]
            }
        ]
    )
    md = convert_to_string(pdf, include_title=False)
    assert "1. First item in list." in md
    assert "2. Second item." in md
    assert "3. Third item." in md


def test_bullet_list_is_detected(tmp_pdf):
    pdf = tmp_pdf(
        [
            {
                "text": [
                    {"text": "\u2022 Alpha", "x": 72, "y": 120, "size": 11},
                    {"text": "\u2022 Beta", "x": 72, "y": 140, "size": 11},
                ]
            }
        ]
    )
    md = convert_to_string(pdf, include_title=False)
    assert "- Alpha" in md
    assert "- Beta" in md
