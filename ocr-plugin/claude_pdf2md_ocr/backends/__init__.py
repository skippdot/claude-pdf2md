from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OcrWord:
    """One recognised word with its page-local bounding box.

    Coordinates are in PDF points (1/72 inch) — the same unit the rest of the
    `claude-pdf2md` model uses. The backend is responsible for converting from
    whatever its native unit is (Tesseract returns pixels).
    """

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float  # 0.0 – 1.0
    line_id: int  # lines within a page that Tesseract grouped together


class OcrBackend(Protocol):
    """Run OCR on a rendered page image and return recognised words.

    `image_bytes` is a PNG of the page at `dpi` resolution. `pdf_width_pt` and
    `pdf_height_pt` are the page dimensions in points, so the backend can scale
    pixel bounding boxes back to point space before returning.
    """

    def recognise(
        self,
        image_bytes: bytes,
        pdf_width_pt: float,
        pdf_height_pt: float,
        dpi: int,
        lang: str,
    ) -> list[OcrWord]: ...
