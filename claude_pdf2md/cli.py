from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .converter import convert


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="claude-pdf2md",
        description="Convert PDF to Markdown with hyperlinks preserved.",
    )
    ap.add_argument("pdf", type=Path, help="Input PDF")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .md (default: stdout)",
    )
    ap.add_argument(
        "--assets",
        type=Path,
        default=None,
        help="Directory to write embedded images (default: images dropped)",
    )
    ap.add_argument(
        "--with-title",
        action="store_true",
        help="Emit the PDF metadata title as H1 (usually redundant with the visible first heading on page 1).",
    )
    ap.add_argument(
        "--diff",
        type=Path,
        default=None,
        help="Directory to write side-by-side render diff PNGs + report.json",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = ap.parse_args(argv)
    if not args.pdf.is_file():
        print(f"error: PDF not found: {args.pdf}", file=sys.stderr)
        return 2

    md = convert(
        args.pdf,
        output=args.output,
        assets_dir=args.assets,
        include_title=args.with_title,
    )
    if args.output is None and args.diff is None:
        sys.stdout.write(md)

    if args.diff is not None:
        from .rendering import render_diff

        report = render_diff(args.pdf, md, args.diff)
        print(
            f"diff: {len(report['pages'])} pages, mean SSIM={report['mean_ssim']:.3f}, written to {args.diff}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
