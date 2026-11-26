"""Downscaled image representations for previews and renders.

Asset-pack PNGs are stored at full source size (2.6-14 MB each in the demo packs). Quick
Reel's Remotion render decodes every one of them in headless Chrome for every frame batch,
which made a 16 s reel take ~70 s. A reel frame is 1080x1920, so anything larger is wasted.

``representation_uri`` returns a copy no larger than ``max_px`` on its long side, created on
first request and cached in object storage next to the original
(``<original key>.max<px>.<ext>``). Images with transparency stay PNG (cut-outs need alpha);
opaque ones become JPEG, which is far smaller. Non-images and images already small enough
return the original URI.
"""

from __future__ import annotations

import io
import logging
from typing import Protocol

from botocore.exceptions import ClientError
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
_JPEG_QUALITY = 88
MIN_REPRESENTATION_PX = 64
MAX_REPRESENTATION_PX = 4096


class _StoredBody(Protocol):
    body: bytes


class RepresentationStorage(Protocol):
    def get_object(self, *, storage_uri: str) -> _StoredBody: ...

    def head_object(self, *, storage_uri: str) -> object: ...

    def put_object(
        self,
        *,
        data: bytes,
        storage_uri: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> object: ...


def is_image_uri(storage_uri: str) -> bool:
    return storage_uri.lower().split("?", 1)[0].endswith(_IMAGE_SUFFIXES)


def representation_uri(
    *,
    storage_uri: str,
    max_px: int,
    storage: RepresentationStorage,
) -> str:
    """URI of a copy of the image at ``storage_uri`` no larger than ``max_px`` (cached)."""

    if not MIN_REPRESENTATION_PX <= max_px <= MAX_REPRESENTATION_PX:
        raise ValueError(f"max_px must be {MIN_REPRESENTATION_PX}-{MAX_REPRESENTATION_PX}")
    if not is_image_uri(storage_uri):
        return storage_uri
    for suffix in (".png", ".jpg"):
        candidate = f"{storage_uri}.max{max_px}{suffix}"
        if _exists(storage, candidate):
            return candidate

    original = storage.get_object(storage_uri=storage_uri)
    body = original.body
    with Image.open(io.BytesIO(body)) as source:
        image = ImageOps.exif_transpose(source) or source
        if max(image.size) <= max_px:
            return storage_uri
        has_alpha = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        image = image.convert("RGBA" if has_alpha else "RGB")
        image.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        if has_alpha:
            image.save(buffer, format="PNG", optimize=True)
            target, content_type = f"{storage_uri}.max{max_px}.png", "image/png"
        else:
            image.save(buffer, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            target, content_type = f"{storage_uri}.max{max_px}.jpg", "image/jpeg"
    storage.put_object(
        data=buffer.getvalue(),
        storage_uri=target,
        content_type=content_type,
        metadata={"derived-from": storage_uri[-200:], "max-px": str(max_px)},
    )
    logger.info(
        "Created %spx representation of %s (%d -> %d bytes)",
        max_px,
        storage_uri,
        len(body),
        buffer.tell(),
    )
    return target


def _exists(storage: RepresentationStorage, storage_uri: str) -> bool:
    try:
        storage.head_object(storage_uri=storage_uri)
    except ClientError:
        return False
    return True


__all__ = [
    "MAX_REPRESENTATION_PX",
    "MIN_REPRESENTATION_PX",
    "is_image_uri",
    "representation_uri",
]
