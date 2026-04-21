# claude-pdf2md-ocr

OCR plugin for [`claude-pdf2md`](https://pypi.org/project/claude-pdf2md/). Detects
PDF pages that have no text layer (e.g. scanned documents, photo-of-paper
exports) and fills them in using Tesseract, so that the existing
`claude-pdf2md` pipeline — headings, lists, tables, links — works on scanned
documents the same way it works on native PDFs.

## Status

Local prototype. Not yet on PyPI. Tracked for release once accuracy on real
scanned Ukrainian legal documents reaches ≥90% word-level recall.

## System dependency

Tesseract must be installed separately.

```bash
# macOS
brew install tesseract tesseract-lang     # ships 100+ language packs

# Debian / Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-ukr tesseract-ocr-rus

# verify
tesseract --list-langs | grep -E '^(ukr|rus|eng)$'
```

## Usage

```bash
claude-pdf2md-ocr scan.pdf -o out.md --lang ukr+rus+eng
```

Or programmatically:

```python
from claude_pdf2md_ocr import convert_with_ocr

md = convert_with_ocr("scan.pdf", lang="ukr+rus+eng")
```
