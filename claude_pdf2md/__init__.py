"""claude-pdf2md — convert PDFs to Markdown while preserving hyperlinks."""

from .converter import PageEnricher, convert, convert_to_string
from .validate import PdfStructureWarning, ValidationIssue, validate_doc

__all__ = [
    "PageEnricher",
    "PdfStructureWarning",
    "ValidationIssue",
    "convert",
    "convert_to_string",
    "validate_doc",
]
__version__ = "0.1.2"
