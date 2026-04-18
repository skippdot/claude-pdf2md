"""claude-pdf2md — convert PDFs to Markdown while preserving hyperlinks."""
from .converter import convert, convert_to_string

__all__ = ["convert", "convert_to_string"]
__version__ = "0.1.0"
