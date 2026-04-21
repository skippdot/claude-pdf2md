"""Command-line entry point: `claude-pdf2md-ocr INPUT.pdf -o OUT.md ...`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import convert_with_ocr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-pdf2md-ocr",
        description="Convert a PDF to Markdown, running Tesseract on pages that have no text layer.",
    )
    parser.add_argument("pdf", type=Path, help="Input PDF path")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output .md file (stdout if omitted)")
    parser.add_argument("--assets", type=Path, default=None, help="Directory to write extracted images to")
    parser.add_argument(
        "--lang",
        default="auto",
        help="Tesseract language spec. `auto` (default) sniffs the document's "
        "existing text layer and picks a narrow pack like `ces+eng`. "
        "Pass an explicit string (e.g. `ukr+rus+eng`) to override.",
    )
    parser.add_argument(
        "--all-pages",
        action="store_true",
        help="Run OCR on every page (default: only pages without a text layer)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.5,
        help="Drop words with Tesseract confidence below this threshold (0.0–1.0). "
        "Empirically 0.5 strips noise tokens (logo glyphs, stray marks) while "
        "keeping real content on Ukrainian/English/Czech legal scans.",
    )
    parser.add_argument("--dpi", type=int, default=200, help="Rasterisation DPI for Tesseract input")
    parser.add_argument(
        "--no-spellcheck",
        dest="spellcheck",
        action="store_false",
        default=True,
        help="Disable cross-script / known-misread post-OCR fixup (spellcheck is on by default).",
    )
    parser.add_argument("--with-title", action="store_true", help="Emit PDF metadata title as an H1 heading")
    args = parser.parse_args(argv)

    if not args.pdf.is_file():
        print(f"error: input file not found: {args.pdf}", file=sys.stderr)
        return 2

    md = convert_with_ocr(
        pdf_path=args.pdf,
        output=args.output,
        assets_dir=args.assets,
        include_title=args.with_title,
        lang=args.lang,
        only_empty_pages=not args.all_pages,
        min_confidence=args.min_confidence,
        dpi=args.dpi,
        spellcheck=args.spellcheck,
    )
    if args.output is None:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
