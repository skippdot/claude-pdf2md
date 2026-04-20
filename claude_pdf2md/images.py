from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .model import Block, Doc

_SAFE_EXT = re.compile(r"^[a-z0-9]{1,8}$")
_DEFAULT_EXT = "png"


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
            # Content-addressable cache key only — never a security primitive,
            # so SHA-1's collision properties are fine and `usedforsecurity=False`
            # keeps it compliant on FIPS-locked hosts.
            digest = hashlib.sha1(img.data, usedforsecurity=False).hexdigest()[:12]
            if digest in cache:
                rel = cache[digest]
            else:
                # `img.ext` is attacker-controlled via the PDF; whitelist to
                # short alphanumerics so `../evil` or `png/../..` can't escape
                # assets_dir and give a malicious PDF an arbitrary-write primitive.
                raw_ext = (img.ext or _DEFAULT_EXT).lower()
                ext = raw_ext if _SAFE_EXT.match(raw_ext) else _DEFAULT_EXT
                fname = f"p{page.number + 1:03d}_{idx + 1:02d}_{digest}.{ext}"
                path = (assets_dir / fname).resolve()
                assets_root = assets_dir.resolve()
                if assets_root not in path.parents:
                    continue
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
