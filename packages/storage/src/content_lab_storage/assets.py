"""Helpers for persisting asset bytes to canonical object-storage locations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from content_lab_storage.checksums import ObjectChecksums, checksum_bytes
from content_lab_storage.client import S3StorageClient, StoredObject
from content_lab_storage.paths import CanonicalStorageLayout

_DEFAULT_FILENAMES = {
    "audio": "audio.mp3",
    "clip": "clip.mp4",
    "image": "image.png",
    "video": "video.mp4",
}
_CONTENT_TYPE_EXTENSIONS = {
    "audio/m4a": ".m4a",
    "audio/mp3": ".mp3",
    "audio/mpeg": ".mp3",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "video/mp4": ".mp4",
}


@dataclass(frozen=True, slots=True)
class StoredAssetBytes:
    """Storage outcome for a canonical asset object write."""

    stored_object: StoredObject
    checksums: ObjectChecksums
    filename: str

    @property
    def storage_uri(self) -> str:
        return self.stored_object.ref.uri


def canonical_asset_filename(
    asset_class: str,
    *,
    content_type: str | None = None,
    filename: str | None = None,
) -> str:
    """Build a stable filename for a ready asset object."""

    if filename is not None:
        normalized_filename = Path(filename).name.strip()
        if not normalized_filename:
            raise ValueError("filename must not be blank")
        return normalized_filename

    normalized_asset_class = asset_class.strip().lower()
    if not normalized_asset_class:
        raise ValueError("asset_class must not be blank")

    extension = None if content_type is None else _CONTENT_TYPE_EXTENSIONS.get(content_type)
    if extension is None:
        return _DEFAULT_FILENAMES.get(normalized_asset_class, "asset.bin")

    stem = normalized_asset_class if normalized_asset_class in _DEFAULT_FILENAMES else "asset"
    return f"{stem}{extension}"


def persist_asset_bytes(
    *,
    client: S3StorageClient,
    layout: CanonicalStorageLayout,
    asset_id: UUID | str,
    asset_class: str,
    data: bytes,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
    filename: str | None = None,
) -> StoredAssetBytes:
    """Upload asset bytes to the canonical derived-asset location."""

    asset_filename = canonical_asset_filename(
        asset_class,
        content_type=content_type,
        filename=filename,
    )
    checksums = checksum_bytes(data)
    stored = client.put_object(
        ref=layout.derived_asset_object(asset_id, asset_filename),
        data=data,
        content_type=content_type,
        metadata=metadata,
        checksum_sha256=checksums.content_hash,
    )
    return StoredAssetBytes(stored_object=stored, checksums=checksums, filename=asset_filename)
