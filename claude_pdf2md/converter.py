from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from . import emit, extract, images, structure, tables
from .validate import PdfStructureWarning, validate_doc

if TYPE_CHECKING:
    import fitz

    from .model import Page


class PageEnricher(Protocol):
    """Post-extract, pre-structure hook. Implementations mutate `page` in place.

    The conversion pipeline runs each enricher once per page, immediately
    after PyMuPDF text extraction and before tables/images/structure/emit.
    This is the point where an out-of-tree plugin — such as an OCR backend —
    can fill in `page.blocks` for scanned pages, so that the downstream
    passes treat the enriched content exactly like native text.

    Pre-work that spans multiple pages (language detection, per-document
    setup) should happen in the caller before the enricher is constructed;
    the hook itself only sees one page at a time.
    """

    def enrich(self, mu_page: fitz.Page, page: Page) -> None: ...


def convert(
    pdf_path: str | Path,
    output: str | Path | None = None,
    assets_dir: str | Path | None = None,
    include_title: bool = False,
    enrichers: list[PageEnricher] | None = None,
    validate: bool = False,
) -> str:
    md = convert_to_string(
        pdf_path,
        assets_dir=assets_dir,
        include_title=include_title,
        enrichers=enrichers,
        validate=validate,
    )
    if output is not None:
        Path(output).write_text(md, encoding="utf-8")
    return md


def convert_to_string(
    pdf_path: str | Path,
    assets_dir: str | Path | None = None,
    include_title: bool = False,
    enrichers: list[PageEnricher] | None = None,
    validate: bool = False,
) -> str:
    pdf_path = str(pdf_path)
    assets_path = Path(assets_dir) if assets_dir is not None else None

    mu, doc = extract.extract_doc(pdf_path)
    try:
        if enrichers:
            for pno, page in enumerate(doc.pages):
                mu_page = mu.load_page(pno)
                for enricher in enrichers:
                    enricher.enrich(mu_page, page)
        tables.apply_tables(mu, doc)
        images.write_assets(doc, assets_path)
        structure.analyze_document(doc)
        if validate:
            for issue in validate_doc(doc):
                page_label = f"page {issue.page_number}" if issue.page_number is not None else "document"
                warnings.warn(
                    f"[{issue.code}] {page_label}: {issue.message}",
                    PdfStructureWarning,
                    stacklevel=2,
                )
        return emit.render(doc, include_title=include_title)
    finally:
        mu.close()
