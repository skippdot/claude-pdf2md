from __future__ import annotations

import hashlib
from pathlib import Path

from .model import Block, Doc


def write_assets(doc: Doc, assets_dir: Path | None) -> None:
    if assets_dir is None:
        for page in doc.pages:
            page.images = []
        return
    assets_dir.mkdir(parents=True, exist_ok=True)
    cache: dict[str, str] = {}
    for page in doc.pages:
        for idx, img in enumerate(page.images):
            if not img.data:
                continue
            digest = hashlib.sha1(img.data).hexdigest()[:12]
            if digest in cache:
                rel = cache[digest]
            else:
                ext = (img.ext or "png").lower()
                fname = f"p{page.number + 1:03d}_{idx + 1:02d}_{digest}.{ext}"
                path = assets_dir / fname
                path.write_bytes(img.data)
                rel = f"{assets_dir.name}/{fname}"
                cache[digest] = rel
            block = Block(
                kind="image",
                lines=[],
                bbox=img.bbox,
                image_path=rel,
                image_alt=f"figure-p{page.number + 1}-{idx + 1}",
            )
            page.blocks.append(block)
        page.blocks.sort(key=lambda b: (b.bbox.y0 if b.bbox else 0.0, b.bbox.x0 if b.bbox else 0.0))
