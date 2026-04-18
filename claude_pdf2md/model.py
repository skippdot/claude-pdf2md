from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal[
    "heading",
    "paragraph",
    "list_item",
    "ordered_item",
    "table",
    "image",
    "code",
]


@dataclass(frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def intersect(self, other: "BBox") -> float:
        ix0 = max(self.x0, other.x0)
        iy0 = max(self.y0, other.y0)
        ix1 = min(self.x1, other.x1)
        iy1 = min(self.y1, other.y1)
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        return (ix1 - ix0) * (iy1 - iy0)

    def overlaps(self, other: "BBox", min_ratio: float = 0.5) -> bool:
        a = self.width * self.height
        if a <= 0:
            return False
        return self.intersect(other) / a >= min_ratio


@dataclass
class Span:
    text: str
    bbox: BBox
    size: float
    font: str
    flags: int
    color: int
    url: str | None = None

    @property
    def bold(self) -> bool:
        # PyMuPDF flag bit 4 = bold; font name containing "Bold" is the reliable
        # fallback for Type3 fonts where the flag isn't populated.
        return bool(self.flags & 16) or ("Bold" in self.font or "bold" in self.font)

    @property
    def italic(self) -> bool:
        return bool(self.flags & 2) or ("Italic" in self.font or "Oblique" in self.font)


@dataclass
class Line:
    spans: list[Span]
    bbox: BBox

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def dominant_size(self) -> float:
        if not self.spans:
            return 0.0
        by_len: dict[float, int] = {}
        for s in self.spans:
            by_len[round(s.size, 1)] = by_len.get(round(s.size, 1), 0) + len(s.text)
        return max(by_len, key=by_len.get)


@dataclass
class Block:
    kind: BlockKind
    lines: list[Line] = field(default_factory=list)
    bbox: BBox | None = None
    level: int = 0
    ordered_index: int | None = None
    indent_level: int = 0
    table_cells: list[list[str]] | None = None
    image_path: str | None = None
    image_alt: str = ""


@dataclass
class LinkAnnot:
    bbox: BBox
    uri: str


@dataclass
class ImageAnnot:
    xref: int
    bbox: BBox
    ext: str
    data: bytes


@dataclass
class Page:
    number: int
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)
    links: list[LinkAnnot] = field(default_factory=list)
    images: list[ImageAnnot] = field(default_factory=list)


@dataclass
class Doc:
    pages: list[Page] = field(default_factory=list)
    body_size: float = 0.0
    heading_sizes: list[float] = field(default_factory=list)
    title: str = ""
