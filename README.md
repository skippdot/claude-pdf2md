# claude-pdf2md

Convert PDFs — especially **Claude Web UI research exports** — into Markdown
with hyperlinks and visual structure preserved, and with a built-in visual
diff to measure how close the rendered Markdown actually looks to the PDF.

## Motivation

Claude Web UI's `research` feature produces two artefacts per report:

- a **PDF** with working hyperlinks on every citation, and
- a **.md** file with the same prose but **all URLs stripped**.

That asymmetry makes the `.md` output nearly useless for downstream work:
quotes without sources, references without destinations, reports you can
re-read but not verify. The PDF keeps the URLs as real PDF link annotations
(rectangles drawn over the glyph run), so the information is present — it just
isn't in the text layer.

`claude-pdf2md` rebuilds the Markdown from the PDF, not from Claude's
textual export, and uses those link annotations as the source of truth for
every citation.

## What it does

End-to-end PDF → Markdown with:

- **100% link recall** via character-level overlay of the PDF's link
  annotation rectangles onto the glyph bounding boxes, so every `[text](url)`
  reflects what the PDF actually linked.
- **Structure detection**: headings (by font-size percentile), bullet and
  numbered lists, paragraph reflow across wrapped lines, tables
  (`fitz.find_tables`), embedded images (dumped to an `assets/` dir).
- **Citation-pill absorption**: Claude's research PDFs render each citation as
  a small-font "pill" floating inline; these would otherwise break up the
  surrounding sentence. The pill blocks are detected by font-size and
  appended to the preceding paragraph.
- **Visual diff as a quality gate**: each page of the source PDF is rendered
  to PNG, the generated Markdown is re-rendered to PDF via WeasyPrint and to
  PNG via PyMuPDF, and the two are compared with SSIM. Side-by-side diff
  images and a JSON report are written for manual inspection.

## Installation

```bash
pip install claude-pdf2md            # core conversion
pip install 'claude-pdf2md[diff]'    # + WeasyPrint-based visual diff
```

Python 3.10+ required. Core depends on PyMuPDF, NumPy, Pillow. The `[diff]`
extra adds `markdown-it-py` and `weasyprint` (which in turn needs cairo/pango
on the host; see WeasyPrint's install notes).

### Windows

```powershell
# 1. Python 3.10+ from python.org (tick "Add Python to PATH" during install)
py -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Core install — pure Python with pre-built wheels, no system deps
pip install claude-pdf2md

# 3. (optional) [diff] extra — needs GTK for WeasyPrint
#    Install "GTK3 runtime" from https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
#    then:
pip install 'claude-pdf2md[diff]'
```

Verify:

```powershell
claude-pdf2md --help
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install claude-pdf2md              # or 'claude-pdf2md[diff]'
```

On Linux, the `[diff]` extra additionally needs `libpango-1.0-0`,
`libpangoft2-1.0-0`, `libharfbuzz0b`, and `fonts-dejavu` (Debian/Ubuntu names;
see WeasyPrint's docs for other distributions).

## CLI

```bash
claude-pdf2md input.pdf -o output.md --assets assets/

# with visual diff against the source pages
claude-pdf2md input.pdf -o output.md --assets assets/ --diff diff/
```

The `--diff` directory will contain one `page_NNN.diff.png` per compared page
(source on the left, rendered Markdown on the right), plus a `report.json`:

```json
{
  "pdf_pages": 15,
  "md_pages":  13,
  "compared":  13,
  "mean_ssim": 0.47,
  "pages": [ { "page": 1, "ssim": 0.47, "pixel_diff_ratio": 0.17, ... } ]
}
```

## Python API

```python
from claude_pdf2md import convert

md = convert(
    "report.pdf",
    output="report.md",
    assets_dir="assets",
)
```

### Plugins via `enrichers=`

As of **0.1.2**, `convert()` / `convert_to_string()` accept an `enrichers`
list. Each enricher is a lightweight Protocol implementation:

```python
class PageEnricher(Protocol):
    def enrich(self, mu_page, page) -> None: ...
```

Enrichers run once per page right after text extraction and before tables /
images / structure / emit, so they can mutate `page.blocks` (add recognised
OCR lines, mark up signatures, drop boilerplate, …) and every downstream
pass treats the result exactly like native text.

The canonical use of this hook is [`claude-pdf2md-ocr`](https://github.com/skippdot/claude-pdf2md-ocr),
which turns scanned PDFs into Markdown by feeding Tesseract output through
the enricher.

### Structural validation

`convert(validate=True)` runs a post-pipeline sanity pass and emits a
`PdfStructureWarning` for each issue it finds:

```python
import warnings
from claude_pdf2md import PdfStructureWarning, convert

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    convert("scan.pdf", output="scan.md", validate=True)

for w in caught:
    if issubclass(w.category, PdfStructureWarning):
        print(w.message)
```

Current checks: empty page, image-only page (likely un-OCR'd scan —
nudges toward `claude-pdf2md-ocr`), heading-level jumps (e.g. H1 → H3
with no H2 in between). Validation is opt-in and silent on a clean
native PDF.

## Alternatives

If you need PDF → Markdown but want a different set of trade-offs:

- **[`pdf2md-claude`](https://github.com/hacker-cb/pdf2md-claude)** — runs
  the PDF through Claude's native-PDF API in ~10-page chunks with
  context carry-over, rebuilds tables with extended thinking, and
  reinjects figures from bounding boxes. Higher fidelity on complex
  layouts, but requires an Anthropic API key, costs per conversion, and
  doesn't work offline. `claude-pdf2md` is the opposite trade: local,
  deterministic, free, fast — and keeps 100% hyperlink recall by reading
  the PDF's link annotations directly rather than asking a model to
  re-discover them.

## How it works

The pipeline (one pass through the PDF, no external OCR):

1. **Extract.** PyMuPDF is read with `rawdict` so every character arrives
   with its own bounding box, font, size, flags and colour.
2. **Link overlay.** For each character, intersect its bbox with the page's
   `get_links()` rectangles; the winning rectangle (≥50% coverage) tags the
   character with a URL. The tag is carried into the span-merge step, so a
   sentence that includes a partial-word link like *"See the report [here](…)
   for details"* comes out with the link on the exact word, not the whole
   line.
3. **Merge characters to spans.** Adjacent characters with identical
   `(font, size, colour, flags, url)` are coalesced; a gap wider than
   `0.6 × fontsize` inserts a literal space.
4. **Structure.** Body-text size is the char-weighted modal font size;
   sizes ≥ `1.10 × body` become heading buckets (H1/H2/H3 by rank). List
   items are detected by their first-line prefix (`1.`, `•`, `-`, …). A
   continuation pass then joins wrapped lines that share the previous
   block's x-indent and have no heading/list marker. Citation pills
   (single-line blocks whose every URL-bearing span is ≥10% smaller than
   body) are folded into the previous paragraph.
5. **Tables & images.** `page.find_tables()` regions become pipe-tables and
   consume the text blocks inside them; embedded images are written to
   `assets/` and referenced with `![alt](path)`.
6. **Emit.** Each block is rendered to Markdown, with consecutive same-URL
   spans collapsed into a single `[...](url)` and adjacent bold runs merged
   around whitespace so the output reads `**new investigations**` rather
   than `**new** **investigations**`.
7. **Visual diff.** `claude-pdf2md ... --diff` renders both sides at the
   same page size and DPI, and reports per-page SSIM + pixel-diff ratio.

## Repository layout

```
claude_pdf2md/
  __init__.py         # public API
  model.py            # BBox, Span, Line, Block, Page, Doc dataclasses
  extract.py          # PyMuPDF → model, char merge, linkage
  links.py            # link-rect → character tagging
  structure.py        # headings, lists, citation & continuation merging
  tables.py           # fitz.find_tables → Markdown tables
  images.py           # embedded-image extraction
  emit.py             # model → Markdown string
  converter.py        # pipeline orchestration
  cli.py              # `claude-pdf2md` entry point
  rendering.py        # MD → HTML → PDF → PNG, page side-by-side
  diff.py             # numpy-only SSIM + coarse pixel diff
tests/
  conftest.py         # synthetic-PDF fixture, optional Bulgaria Watch PDF
  test_links.py       # link recall, no spurious links, partial-word links
  test_structure.py   # heading + list detection
  test_emit.py        # table rendering, bold-run merging
  test_diff.py        # SSIM/pixel-diff sanity checks
  test_integration.py # end-to-end on the Bulgaria Watch research PDF
```

## Limitations (v0.1)

- **Typographic fidelity** is structural, not pixel-level. The diff uses a
  neutral serif font for the Markdown side, so SSIM against the original
  Georgia/Type3 PDF sits around 0.4–0.5 even when the content lines up
  correctly. Treat the SSIM score as "layout preserved" vs "layout broken",
  not "visual match".
- **No OCR**. Scanned PDFs without a text layer produce empty Markdown.
- **Heading levels** cap at H3 based on the three largest heading sizes in
  the document. Deeper hierarchies are flattened.
- **Footnotes / endnotes** aren't split out into a footnote section; they
  appear inline at the position they occur.
- **Two-column layouts** are read in PyMuPDF's default order, which is
  usually top-to-bottom-per-column but not guaranteed.

## License

MIT — see `LICENSE`.

Note that PyMuPDF, this project's primary runtime dependency, is AGPL-3.0 (or
commercial). Distributing `claude-pdf2md` together with PyMuPDF binaries
subjects the combined distribution to AGPL obligations. The
`claude-pdf2md` source itself remains MIT.
