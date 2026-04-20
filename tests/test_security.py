"""Security-regression tests.

These cover attack scenarios that were identified by the initial code review:
  - path traversal through attacker-controlled image extensions;
  - XSS via `javascript:` / `data:` / `file:` URL schemes in link annotations;
  - SSRF / local-file disclosure via WeasyPrint's default URL fetcher when
    rendering markdown to PDF for the diff pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_pdf2md.emit import _safe_url
from claude_pdf2md.images import write_assets
from claude_pdf2md.model import BBox, Doc, ImageAnnot, Page


def _page_with_image(ext: str, data: bytes = b"\x89PNG\r\n\x1a\nfake") -> Doc:
    page = Page(number=0, width=595, height=842)
    page.images = [ImageAnnot(xref=1, bbox=BBox(0, 0, 100, 100), ext=ext, data=data)]
    return Doc(pages=[page])


# ---------------------------------------------------------------------------
# Path traversal via img.ext
# ---------------------------------------------------------------------------


def test_image_extension_traversal_is_blocked(tmp_path: Path):
    # A hostile PDF returning a crafted ext like "png/../../etc/evil" must
    # never let us write outside the assets directory.
    doc = _page_with_image(ext="png/../../../etc/evil")
    write_assets(doc, tmp_path)

    outside = tmp_path.parent / "etc"
    assert not outside.exists(), "traversal escaped the assets directory"
    # Whatever was written must sit under tmp_path.
    written = list(tmp_path.rglob("*"))
    for p in written:
        assert tmp_path in p.resolve().parents or p == tmp_path


def test_image_extension_with_slash_falls_back_to_png(tmp_path: Path):
    doc = _page_with_image(ext="jpg/../evil.sh")
    write_assets(doc, tmp_path)
    files = list(tmp_path.glob("*.png"))
    assert files, "should have fallen back to .png extension"


def test_image_extension_with_null_byte_falls_back(tmp_path: Path):
    doc = _page_with_image(ext="png\x00.exe")
    write_assets(doc, tmp_path)
    files = list(tmp_path.iterdir())
    assert all(f.suffix == ".png" for f in files), files


def test_image_legitimate_extension_is_kept(tmp_path: Path):
    doc = _page_with_image(ext="jpeg")
    write_assets(doc, tmp_path)
    files = list(tmp_path.glob("*.jpeg"))
    assert files


# ---------------------------------------------------------------------------
# URL scheme whitelist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox",
        "file:///etc/passwd",
        "jar:http://evil/!/",
    ],
)
def test_dangerous_url_schemes_are_stripped(url: str):
    assert _safe_url(url) is None, f"dangerous scheme leaked through: {url!r}"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com/path?q=1",
        "mailto:user@example.com",
        "tel:+1-555-0100",
        "ftp://files.example.com/x",
    ],
)
def test_safe_url_schemes_pass_through(url: str):
    assert _safe_url(url) is not None


def test_whitespace_in_url_is_percent_encoded():
    # A URI with embedded newline or tab could break out of the parens or
    # inject a newline into the markdown output.
    assert " " not in (_safe_url("https://example.com/with space") or "")
    assert "\n" not in (_safe_url("https://example.com/\n") or "")
    assert "\t" not in (_safe_url("https://example.com/\t") or "")


def test_dangerous_url_drops_link_but_preserves_text():
    # End-to-end: a PDF with a javascript: URL should still show the text
    # in the output, just without the link wrapper.
    from claude_pdf2md.emit import _tokens_to_md

    tokens = [
        ("Click me", "javascript:alert(1)", False, False),
    ]
    out = _tokens_to_md(tokens)
    assert "Click me" in out
    assert "javascript:" not in out
    assert "](javascript:" not in out


# ---------------------------------------------------------------------------
# WeasyPrint external-resource blocking
# ---------------------------------------------------------------------------


def test_weasyprint_refuses_external_resources():
    pytest.importorskip("weasyprint")
    pytest.importorskip("markdown_it")
    from claude_pdf2md.rendering import _blocking_url_fetcher

    with pytest.raises(ValueError, match="external resource blocked"):
        _blocking_url_fetcher("http://attacker.example/beacon")
    with pytest.raises(ValueError, match="external resource blocked"):
        _blocking_url_fetcher("file:///etc/passwd")
