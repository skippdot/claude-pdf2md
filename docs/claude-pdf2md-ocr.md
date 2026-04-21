# `claude-pdf2md-ocr` — design & plan

> **Status (2026-04-21):** plugin lives in its own repo at
> **<https://github.com/skippdot/claude-pdf2md-ocr>**. Prototype, not yet on
> PyPI. This document retains the design rationale that informed the
> extraction; day-to-day work happens over there.

## Why a separate package

`claude-pdf2md` handles PDFs with an existing text layer: PyMuPDF gives us chars, fonts, spans, link annotations, so the whole pipeline is deterministic and fast. Scanned PDFs (and hybrid PDFs where only the cover page has a text layer, like the insurance contract in `output3.md`) have no text to extract — every page comes through as a figure placeholder.

OCR is a fundamentally different kind of work:

- **Weight.** Tesseract adds ~300 MB (binary + language packs for ukr/rus/eng). PaddleOCR pulls PyTorch (~1 GB with models). The base `claude-pdf2md` install is ~50 MB — we don't want to 10–20× that for users who only need the text-layer path.
- **Accuracy shape.** OCR output is probabilistic: 95–98% on good scans, lower on noisy ones. For legal documents a 1:1 match is **not achievable**. The package needs review/validation affordances (confidence per word, bounding boxes, per-page side-by-side) that are irrelevant to the text-layer path.
- **Testing profile.** OCR tests are slow and fixture-heavy; running them on every commit would double CI time on the base repo for no benefit.

Decision: ship `claude-pdf2md-ocr` as a **separate PyPI package** that **depends on `claude-pdf2md`** and extends it through a small hook point. Not a fork, not an extra.

## Minimum hook in the core package

Today `claude_pdf2md/extract.py:_extract_page` reads PyMuPDF's char stream and builds a `Page`. When a page has no text layer, the embedded images survive (and `images.write_assets` emits `![figure-...]`) but the `Page.blocks` comes back text-less.

The OCR plugin needs exactly one seam:

1. **Detect text-empty pages.** After `_extract_page` returns, if `page.blocks` contains no text-bearing blocks, the page is a candidate for OCR.
2. **Run OCR on the rendered page.** Plugin renders the page to a PNG (PyMuPDF `page.get_pixmap`), runs OCR, receives `(text, bbox, confidence)` per word.
3. **Inject synthetic spans.** The plugin builds `Line` / `Span` objects from OCR output and drops them back into `Page.blocks`. Every downstream pass (`structure.analyze_document`, `tables.apply_tables`, `emit.render`) already operates on `Page` / `Block` / `Line` / `Span` — they don't care that the spans came from OCR.

What the core has to expose (≈30 lines in `converter.py`):

```python
# claude_pdf2md/converter.py
from typing import Protocol

class PageEnricher(Protocol):
    def enrich(self, mu_page, page: Page) -> None: ...

def convert_to_string(..., enrichers: list[PageEnricher] | None = None) -> str:
    ...
    mu, doc = extract.extract_doc(pdf_path)
    try:
        if enrichers:
            for mu_pno in range(mu.page_count):
                page = doc.pages[mu_pno]
                for enricher in enrichers:
                    enricher.enrich(mu.load_page(mu_pno), page)
        tables.apply_tables(mu, doc)
        ...
```

That's the whole API. No plugin registry, no entry points yet — callers pass enrichers explicitly. Entry-point auto-discovery (so `pip install claude-pdf2md-ocr` enables `claude-pdf2md input.pdf --ocr` out of the box) is a v0.2 follow-up.

## Package shape: `claude-pdf2md-ocr`

```
claude-pdf2md-ocr/
├── claude_pdf2md_ocr/
│   ├── __init__.py             # __version__
│   ├── __main__.py             # python -m claude_pdf2md_ocr
│   ├── cli.py                  # claude-pdf2md-ocr  (own entry point)
│   ├── enricher.py             # OcrEnricher — implements PageEnricher
│   ├── backends/
│   │   ├── __init__.py         # Backend protocol (recognize(png_bytes, lang) -> list[OcrWord])
│   │   ├── tesseract.py        # pytesseract backend (default)
│   │   └── paddle.py           # PaddleOCR backend (optional, paddle extra)
│   └── inject.py               # OcrWord → Span/Line/Block builders
├── tests/
│   ├── fixtures/
│   │   └── scanned_3pg.pdf     # tiny synthetic scan via reportlab or rasterizing a known-text PDF
│   ├── test_backend_tesseract.py
│   └── test_roundtrip_with_ocr.py
├── pyproject.toml
├── README.md
└── LICENSE
```

`pyproject.toml` (key bits):

```toml
[project]
name = "claude-pdf2md-ocr"
dependencies = [
    "claude-pdf2md>=0.1.0",
    "pytesseract>=0.3.10",   # wraps system tesseract binary
]

[project.optional-dependencies]
paddle = ["paddleocr>=2.7"]  # heavier alternative backend

[project.scripts]
claude-pdf2md-ocr = "claude_pdf2md_ocr.cli:main"
```

System dependency: the `tesseract` binary with language packs must be installed separately (`brew install tesseract tesseract-lang` on macOS, `apt-get install tesseract-ocr tesseract-ocr-ukr tesseract-ocr-rus` on Linux). README documents this prominently; CLI fails with a clear error on first run if binary is missing.

## CLI

```bash
claude-pdf2md-ocr input.pdf -o output.md \
  --lang ukr+rus+eng \
  --only-empty-pages \                # default: OCR only pages with no text layer
  --assets ./assets/ \
  --min-confidence 0.5 \
  --backend tesseract                 # or --backend paddle
```

Flags inherited from base tool (`--assets`, `-o`, `--with-title`, `--diff`) work the same — the CLI wraps `convert_to_string(..., enrichers=[OcrEnricher(...)])`.

## Testing strategy

- **Unit test for `OcrEnricher`** — uses a synthetic `Page` with an empty `blocks` list and a stub backend that returns known `(word, bbox, confidence)` tuples. No real OCR involved.
- **Integration test** — pytest marker `ocr_live` that requires `tesseract` on PATH. Generates a PDF from known Markdown (reusing `rendering.markdown_to_pdf_bytes` from the base package's `[diff]` extra), rasterises it so the text layer is gone, runs OCR, asserts the recognised text matches ≥95% by word-set diff. Gated by marker so it doesn't block CI unless explicitly opted in.
- **CI** — basic matrix (py3.10–3.14) runs unit tests only. A nightly / manual workflow runs the `ocr_live` tests after installing `tesseract-ocr tesseract-ocr-ukr tesseract-ocr-rus`.

## Risks / open questions

1. **Accuracy floor for legal Ukrainian text.** Cyrillic with diacritics and closely-shaped letters (`и/і/ї`, `е/є`) are the hard cases. Needs benchmark on the real user fixture (`Шамаєв СС Дог страх майна 260625.pdf`) before committing to a target number in the README.
2. **Table reconstruction.** Tesseract returns word boxes, not table structure. The existing `structure._detect_visual_tables` works on block geometry — if OCR produces one block per cell (via Tesseract's paragraph/line levels) it should reuse the existing path; otherwise we need a dedicated OCR-table step. Probe in the first benchmark.
3. **Reading order.** OCR word order is left-to-right top-to-bottom, but layouts with columns or sidebars need clustering before injection. Start simple (trust Tesseract's line order), add clustering only if benchmark shows it's needed.
4. **Hybrid pages.** When a page has *some* text layer plus scanned regions (rare but possible), running OCR only on "empty" pages misses the scanned region. Deferred; `--only-empty-pages=false` can be added later to OCR everything.

## Phasing

- **v0.1** — Tesseract backend, `--only-empty-pages`, unit + one integration test, README with setup instructions, published to PyPI.
- **v0.2** — entry-point auto-discovery in base package (`claude-pdf2md input.pdf --ocr` works when plugin is installed), per-word confidence in output as optional HTML comment blocks.
- **v0.3** — PaddleOCR backend, benchmarking harness on a real fixture set, table-structure recovery if step 2 above proves to need it.

## Immediate next steps

1. Publish `claude-pdf2md` v0.1.0 to PyPI so the plugin has a pinnable dependency.
2. Add the `enrichers=` seam to `converter.py` in `claude-pdf2md` v0.1.1 (small, shippable).
3. Scaffold `claude-pdf2md-ocr` as a sibling git repo and publish v0.1.0 with Tesseract backend only.
4. Benchmark on the insurance contract; report accuracy + where it fails; adjust scope.
