"""Helpers for staged asset persistence metadata and state transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

PERSISTENCE_METADATA_KEY = "storage"


@dataclass(frozen=True, slots=True)
class AssetMediaMetadata:
    """Optional media metadata captured alongside persisted asset bytes."""

    width: int | None = None
    height: int | None = None
    fps: int | None = None
    duration_seconds: float | int | None = None

    def as_metadata(self) -> dict[str, int | float]:
        metadata: dict[str, int | float] = {}
        if self.width is not None:
            metadata["width"] = self.width
        if self.height is not None:
            metadata["height"] = self.height
        if self.fps is not None:
            metadata["fps"] = self.fps
        if self.duration_seconds is not None:
            metadata["duration_seconds"] = self.duration_seconds
        return metadata


@dataclass(frozen=True, slots=True)
class AssetPersistenceFailure:
    """Failure details retained for later asset-storage reconciliation."""

    stage: str
    message: str
    error_type: str

    def as_metadata(self) -> dict[str, str]:
        return {
            "stage": self.stage,
            "message": self.message,
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class AssetPersistenceRecord:
    """Database-facing persistence outcome for a stored asset object."""

    storage_uri: str
    content_hash: str
    size_bytes: int | None = None
    content_type: str | None = None
    media_metadata: AssetMediaMetadata = field(default_factory=AssetMediaMetadata)


def merge_asset_metadata(
    existing: Mapping[str, Any] | None = None,
    *,
    media_metadata: AssetMediaMetadata | None = None,
    state: str | None = None,
    storage_uri: str | None = None,
    content_hash: str | None = None,
    size_bytes: int | None = None,
    content_type: str | None = None,
    failure: AssetPersistenceFailure | None = None,
) -> dict[str, Any]:
    """Merge persistence state into asset metadata without dropping prior fields."""

    metadata = dict(existing or {})
    if media_metadata is not None:
        metadata.update(media_metadata.as_metadata())

    storage_metadata = _storage_metadata(metadata)
    if state is not None:
        storage_metadata["state"] = state
    if storage_uri is not None:
        storage_metadata["storage_uri"] = storage_uri
    if content_hash is not None:
        storage_metadata["content_hash"] = content_hash
    if size_bytes is not None:
        storage_metadata["size_bytes"] = size_bytes
    if content_type is not None:
        storage_metadata["content_type"] = content_type
    if failure is not None:
        storage_metadata["failure"] = failure.as_metadata()
    elif state == "ready":
        storage_metadata.pop("failure", None)

    if storage_metadata:
        metadata[PERSISTENCE_METADATA_KEY] = storage_metadata
    return metadata


def _storage_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    current = metadata.get(PERSISTENCE_METADATA_KEY)
    if isinstance(current, Mapping):
        return dict(current)
    return {}
