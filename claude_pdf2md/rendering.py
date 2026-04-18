from __future__ import annotations

import io
import json
from pathlib import Path

import fitz
import numpy as np
from PIL import Image

from .diff import pixel_diff, ssim

_DEFAULT_DPI = 140


def render_diff(
    pdf_path: str | Path,
    markdown_text: str,
    out_dir: str | Path,
    dpi: int = _DEFAULT_DPI,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_pages = render_pdf_pages(pdf_path, dpi=dpi)
    candidate_pdf = markdown_to_pdf_bytes(markdown_text, page_size=source_pages[0].size)
    candidate_pages = render_pdf_bytes_pages(candidate_pdf, dpi=dpi)

    n = min(len(source_pages), len(candidate_pages))
    page_reports = []
    total_ssim = 0.0
    for i in range(n):
        src = source_pages[i]
        cand = _resize_to_width(candidate_pages[i], src.size[0])
        if cand.size[1] != src.size[1]:
            cand = _pad_or_crop_height(cand, src.size[1])
        diff_path = out_dir / f"page_{i + 1:03d}.diff.png"
        _save_side_by_side(src, cand, diff_path)
        score = ssim(np.asarray(src.convert("L"), dtype=np.float32), np.asarray(cand.convert("L"), dtype=np.float32))
        pix = pixel_diff(np.asarray(src.convert("RGB")), np.asarray(cand.convert("RGB")))
        page_reports.append(
            {
                "page": i + 1,
                "ssim": round(float(score), 4),
                "pixel_diff_ratio": round(float(pix), 4),
                "diff_image": diff_path.name,
            }
        )
        total_ssim += float(score)

    report = {
        "pdf_pages": len(source_pages),
        "md_pages": len(candidate_pages),
        "compared": n,
        "mean_ssim": round(total_ssim / n, 4) if n else 0.0,
        "pages": page_reports,
        "dpi": dpi,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def render_pdf_pages(pdf_path: str | Path, dpi: int = _DEFAULT_DPI) -> list[Image.Image]:
    doc = fitz.open(str(pdf_path))
    try:
        return [_pixmap_to_image(p.get_pixmap(dpi=dpi)) for p in doc]
    finally:
        doc.close()


def render_pdf_bytes_pages(pdf_bytes: bytes, dpi: int = _DEFAULT_DPI) -> list[Image.Image]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [_pixmap_to_image(p.get_pixmap(dpi=dpi)) for p in doc]
    finally:
        doc.close()


def markdown_to_pdf_bytes(
    md_text: str,
    page_size: tuple[int, int] | None = None,
) -> bytes:
    from markdown_it import MarkdownIt
    from weasyprint import CSS, HTML

    md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")
    body = md.render(md_text)
    html = _wrap_html(body)
    css = _default_css(page_size)
    return HTML(string=html).write_pdf(stylesheets=[CSS(string=css)])


def _wrap_html(body_html: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'></head><body>"
        + body_html
        + "</body></html>"
    )


def _default_css(page_size: tuple[int, int] | None) -> str:
    # A4-ish by default; if we have the source page size in pixels at 140dpi
    # we can recover approximate mm to keep the two renderings proportional.
    if page_size:
        w_px, h_px = page_size
        w_mm = w_px / _DEFAULT_DPI * 25.4
        h_mm = h_px / _DEFAULT_DPI * 25.4
        size_rule = f"size: {w_mm:.1f}mm {h_mm:.1f}mm"
    else:
        size_rule = "size: A4"
    return (
        "@page { "
        + size_rule
        + "; margin: 15mm; } "
        "body { font-family: Georgia, 'DejaVu Serif', serif; font-size: 11pt; line-height: 1.45; color: #111; } "
        "h1 { font-size: 20pt; margin-top: 0; } "
        "h2 { font-size: 15pt; } "
        "h3 { font-size: 13pt; } "
        "a { color: #1a5490; text-decoration: none; } "
        "table { border-collapse: collapse; width: 100%; margin: 8pt 0; } "
        "th, td { border: 1px solid #888; padding: 4pt 6pt; vertical-align: top; font-size: 10pt; } "
        "img { max-width: 100%; } "
        "p, li { orphans: 2; widows: 2; }"
    )


def _pixmap_to_image(pix: fitz.Pixmap) -> Image.Image:
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _resize_to_width(img: Image.Image, target_w: int) -> Image.Image:
    if img.width == target_w:
        return img
    ratio = target_w / img.width
    return img.resize((target_w, max(1, int(img.height * ratio))), Image.LANCZOS)


def _pad_or_crop_height(img: Image.Image, target_h: int) -> Image.Image:
    if img.height == target_h:
        return img
    if img.height > target_h:
        return img.crop((0, 0, img.width, target_h))
    bg = Image.new("RGB", (img.width, target_h), (255, 255, 255))
    bg.paste(img, (0, 0))
    return bg


def _save_side_by_side(a: Image.Image, b: Image.Image, path: Path) -> None:
    combined = Image.new("RGB", (a.width + b.width + 8, max(a.height, b.height)), (240, 240, 240))
    combined.paste(a, (0, 0))
    combined.paste(b, (a.width + 8, 0))
    combined.save(path, format="PNG", optimize=True)
