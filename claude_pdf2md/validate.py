"""Post-conversion structural sanity checks.

Run after extract → enrichers → tables → images → structure, before emit.
The goal is to catch the kinds of silent data loss that PDF pipelines
produce but don't surface: a page whose text never made it into the
output, a scanned page no OCR plugin was attached to, or a heading level
that jumped from H1 to H3 with no H2 in between.

Validation is opt-in via `convert_to_string(validate=True)` — on a clean
native PDF it produces zero issues, but on hybrid scans or unusual
layouts it points the user at the specific page that needs attention.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Doc, Page


class PdfStructureWarning(UserWarning):
    """Warning class for structural issues surfaced by `validate_doc`.

    Subclassing `UserWarning` lets callers filter these specifically via
    `warnings.filterwarnings("ignore", category=PdfStructureWarning)`
    without suppressing unrelated warnings from the rest of the stack."""


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    page_number: int | None  # 1-indexed page number; None means document-level.
    message: str


def validate_doc(doc: Doc) -> list[ValidationIssue]:
    """Return a list of structural issues found in `doc`.

    Checks are intentionally narrow — each one corresponds to a concrete
    failure mode we've seen in real documents. Adding noisy heuristics
    here has a bigger cost than here than missing them, because callers
    will stop trusting the warnings the first time one is spurious.
    """
    issues: list[ValidationIssue] = []
    for page in doc.pages:
        issues.extend(_check_page(page))
    issues.extend(_check_heading_hierarchy(doc))
    return issues


def _check_page(page: Page) -> list[ValidationIssue]:
    text_chars = sum(len(line.text.strip()) for block in page.blocks if block.kind != "image" for line in block.lines)
    image_blocks = [block for block in page.blocks if block.kind == "image"]
    if not page.blocks:
        return [
            ValidationIssue(
                code="empty_page",
                page_number=page.number,
                message="Page produced no blocks — the PDF page may be blank, or upstream extraction dropped it.",
            )
        ]
    if text_chars == 0 and image_blocks:
        return [
            ValidationIssue(
                code="text_free_page_with_image",
                page_number=page.number,
                # Names claude-pdf2md-ocr explicitly because a whole-page raster
                # with no text layer is the exact shape that plugin was built for.
                message=(
                    "Page has only image content and no recognised text — likely a scan; consider claude-pdf2md-ocr."
                ),
            )
        ]
    return []


def _check_heading_hierarchy(doc: Doc) -> list[ValidationIssue]:
    """Flag heading-level jumps of ≥ 2 (e.g. H1 directly followed by H3)."""
    issues: list[ValidationIssue] = []
    last_level = 0
    for page in doc.pages:
        for block in page.blocks:
            if block.kind != "heading":
                continue
            level = block.level or 1
            if last_level and level > last_level + 1:
                issues.append(
                    ValidationIssue(
                        code="heading_level_jump",
                        page_number=page.number,
                        message=f"Heading level jumped from H{last_level} to H{level} with no intermediate level.",
                    )
                )
            last_level = level
    return issues
