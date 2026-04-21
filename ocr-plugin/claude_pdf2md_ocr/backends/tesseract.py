"""Tesseract backend: wraps `pytesseract.image_to_data` and scales bboxes
from pixels (image space) back to points (PDF space).

Tesseract is invoked per page image — `recognise` takes exactly one page's
PNG. Word-level output is requested (`output_type=DICT`) because we need
bounding boxes; line-level would lose positions."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from . import OcrBackend, OcrWord


class TesseractBackend(OcrBackend):
    def __init__(self, psm: int = 6) -> None:
        # PSM 6 — "assume a single uniform block of text." Works well on
        # typical legal/scan pages. PSM 3 (default, "auto") often over-splits
        # multi-column Ukrainian legal pages.
        self._psm = psm

    def recognise(
        self,
        image_bytes: bytes,
        pdf_width_pt: float,
        pdf_height_pt: float,
        dpi: int,
        lang: str,
    ) -> list[OcrWord]:
        import pytesseract

        img = Image.open(BytesIO(image_bytes))
        px_w, px_h = img.size
        sx = pdf_width_pt / px_w
        sy = pdf_height_pt / px_h

        config = f"--psm {self._psm}"
        data = pytesseract.image_to_data(img, lang=lang, config=config, output_type=pytesseract.Output.DICT)

        words: list[OcrWord] = []
        for i, text in enumerate(data["text"]):
            if not text or not text.strip():
                continue
            conf_raw = data["conf"][i]
            try:
                conf = float(conf_raw) / 100.0
            except (TypeError, ValueError):
                continue
            if conf < 0:  # Tesseract uses -1 for "no confidence computed"
                continue
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            # Tesseract groups words into (block, par, line); combine the two
            # sub-page-level keys into one stable line id so our injector can
            # cluster words into lines without reinventing the wheel.
            line_id = data["block_num"][i] * 10_000 + data["par_num"][i] * 100 + data["line_num"][i]
            words.append(
                OcrWord(
                    text=text,
                    x0=x * sx,
                    y0=y * sy,
                    x1=(x + w) * sx,
                    y1=(y + h) * sy,
                    confidence=conf,
                    line_id=line_id,
                )
            )
        return words
