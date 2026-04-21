"""claude-pdf2md — convert PDFs to Markdown while preserving hyperlinks."""

from .converter import PageEnricher, convert, convert_to_string

__all__ = ["PageEnricher", "convert", "convert_to_string"]
__version__ = "0.1.2"
