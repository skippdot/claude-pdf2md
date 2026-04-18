from __future__ import annotations

from pathlib import Path

from . import emit, extract, images, structure, tables


def convert(
    pdf_path: str | Path,
    output: str | Path | None = None,
    assets_dir: str | Path | None = None,
    include_title: bool = True,
) -> str:
    md = convert_to_string(pdf_path, assets_dir=assets_dir, include_title=include_title)
    if output is not None:
        Path(output).write_text(md, encoding="utf-8")
    return md


def convert_to_string(
    pdf_path: str | Path,
    assets_dir: str | Path | None = None,
    include_title: bool = True,
) -> str:
    pdf_path = str(pdf_path)
    assets_path = Path(assets_dir) if assets_dir is not None else None

    mu, doc = extract.extract_doc(pdf_path)
    try:
        tables.apply_tables(mu, doc)
        images.write_assets(doc, assets_path)
        structure.analyze_document(doc)
        return emit.render(doc, include_title=include_title)
    finally:
        mu.close()
