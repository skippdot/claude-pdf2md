from __future__ import annotations

import re

from claude_pdf2md import convert


def test_bulgaria_watch_end_to_end(bulgaria_watch_pdf, tmp_path):
    out_md = tmp_path / "out.md"
    assets = tmp_path / "assets"
    md = convert(bulgaria_watch_pdf, output=out_md, assets_dir=assets)
    assert out_md.is_file()
    assert len(md) > 10_000

    assert md.count("## #") >= 5

    urls = set(re.findall(r"\]\(([^)]+)\)", md))
    assert len(urls) >= 50

    assert "https://ec.europa.eu/eurostat" in md
    assert "Bulgaria Watch" in md


def test_bulgaria_watch_visual_diff_reasonable(bulgaria_watch_pdf, tmp_path):
    from claude_pdf2md.rendering import render_diff

    md = convert(bulgaria_watch_pdf)
    report = render_diff(bulgaria_watch_pdf, md, tmp_path / "diff")
    assert report["compared"] >= 10
    # With different fonts and paginations, anything over 0.3 demonstrates
    # that the structural content lines up; below that would signal that the
    # emitter lost whole sections or reordered them badly.
    assert report["mean_ssim"] > 0.30, report
