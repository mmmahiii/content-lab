"""Pre-render validation for layered composition manifests and source assets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Protocol

from content_lab_editing.composition_manifest import (
    AUDIO_MEDIA_TYPES,
    BACKGROUND_MEDIA_TYPES,
    VISUAL_MEDIA_TYPES,
    CompositionLayer,
    CompositionManifest,
)

READY_ASSET_STATUSES = frozenset({"ready"})
SUPPORTED_EXPORT_CONTAINERS = frozenset({"mp4"})


class StorageObjectProbe(Protocol):
    """Minimal storage surface needed for pre-render existence checks."""

    def head_object(self, *, storage_uri: str) -> object:
        """Return object metadata for an S3/MinIO URI or raise when missing."""


@dataclass(frozen=True, slots=True)
class SourceAssetReference:
    """Source metadata used to validate a composition input before rendering."""

    source: str | PathLike[str]
    media_type: str | None = None
    content_hash: str | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class CompositionPreflightIssue:
    """Operator-readable validation issue for a composition preflight check."""

    code: str
    message: str
    asset_id: str | None = None
    layer_id: str | None = None


class CompositionPreflightError(ValueError):
    """Raised when a composition cannot safely proceed to rendering."""

    def __init__(self, issues: Sequence[CompositionPreflightIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(_format_preflight_error(self.issues))


SourceAssetInput = str | PathLike[str] | SourceAssetReference | Mapping[str, object]


def validate_composition_manifest(manifest: CompositionManifest) -> list[CompositionPreflightIssue]:
    """Return structural manifest issues that should stop FFmpeg execution."""

    issues: list[CompositionPreflightIssue] = []
    if manifest.canvas_width <= 0 or manifest.canvas_height <= 0:
        issues.append(
            CompositionPreflightIssue(
                code="invalid_canvas_dimensions",
                message="canvas dimensions must be positive integers",
            )
        )
    if manifest.duration <= 0:
        issues.append(
            CompositionPreflightIssue(
                code="invalid_duration",
                message="composition duration must be greater than zero",
            )
        )
    if manifest.fps <= 0:
        issues.append(
            CompositionPreflightIssue(code="invalid_fps", message="fps must be greater than zero")
        )

    _validate_layer_window(
        manifest.background_layer,
        duration=manifest.duration,
        allowed_media_types=BACKGROUND_MEDIA_TYPES,
        collection_name="background_layer",
        issues=issues,
    )
    if manifest.background_layer.start_time != 0:
        issues.append(
            CompositionPreflightIssue(
                code="background_start_time_invalid",
                message="background_layer must start at 0",
                asset_id=manifest.background_layer.asset_id,
                layer_id=manifest.background_layer.layer_id,
            )
        )
    if manifest.background_layer.end_time < manifest.duration:
        issues.append(
            CompositionPreflightIssue(
                code="background_duration_incomplete",
                message="background_layer must cover the composition duration",
                asset_id=manifest.background_layer.asset_id,
                layer_id=manifest.background_layer.layer_id,
            )
        )

    for layer in manifest.layers:
        _validate_layer_window(
            layer,
            duration=manifest.duration,
            allowed_media_types=VISUAL_MEDIA_TYPES,
            collection_name="layers",
            issues=issues,
        )
    for layer in manifest.audio_layers:
        _validate_layer_window(
            layer,
            duration=manifest.duration,
            allowed_media_types=AUDIO_MEDIA_TYPES,
            collection_name="audio_layers",
            issues=issues,
        )

    z_values = [layer.z_index for layer in manifest.layers]
    if z_values != sorted(z_values):
        issues.append(
            CompositionPreflightIssue(
                code="z_index_order_invalid",
                message="visual layers must be sorted by ascending z_index",
            )
        )
    if len(set(z_values)) != len(z_values):
        issues.append(
            CompositionPreflightIssue(
                code="z_index_duplicate",
                message="visual layer z_index values must be unique",
            )
        )
    if manifest.layers and manifest.background_layer.z_index >= min(z_values):
        issues.append(
            CompositionPreflightIssue(
                code="background_z_index_invalid",
                message="background_layer z_index must be lower than visual layers",
                asset_id=manifest.background_layer.asset_id,
                layer_id=manifest.background_layer.layer_id,
            )
        )

    layer_ids = [
        layer.layer_id for layer in [manifest.background_layer, *manifest.layers, *manifest.audio_layers]
    ]
    if len(set(layer_ids)) != len(layer_ids):
        issues.append(
            CompositionPreflightIssue(
                code="layer_id_duplicate",
                message="layer_id values must be unique within a composition manifest",
            )
        )

    preset = manifest.export_preset
    if preset.container not in SUPPORTED_EXPORT_CONTAINERS:
        issues.append(
            CompositionPreflightIssue(
                code="export_preset_invalid",
                message=f"export preset container {preset.container!r} is not supported",
            )
        )
    for field_name, value in {
        "video_codec": preset.video_codec,
        "audio_codec": preset.audio_codec,
        "pixel_format": preset.pixel_format,
        "preset": preset.preset,
        "audio_bitrate": preset.audio_bitrate,
    }.items():
        if not value.strip():
            issues.append(
                CompositionPreflightIssue(
                    code="export_preset_invalid",
                    message=f"export preset {field_name} must not be empty",
                )
            )

    return issues


def validate_source_asset_availability(
    manifest: CompositionManifest,
    *,
    asset_sources: Mapping[str, SourceAssetInput],
    storage_client: StorageObjectProbe | None = None,
    require_content_hash: bool = True,
) -> list[CompositionPreflightIssue]:
    """Return source asset issues that should stop layered rendering."""

    issues: list[CompositionPreflightIssue] = []
    seen_asset_ids: set[str] = set()
    for layer in [manifest.background_layer, *manifest.layers, *manifest.audio_layers]:
        if layer.asset_id in seen_asset_ids:
            continue
        seen_asset_ids.add(layer.asset_id)

        raw_source = asset_sources.get(layer.asset_id)
        if raw_source is None:
            issues.append(
                CompositionPreflightIssue(
                    code="asset_source_missing",
                    message=f"missing asset source for asset_id {layer.asset_id!r}",
                    asset_id=layer.asset_id,
                    layer_id=layer.layer_id,
                )
            )
            continue

        ref = coerce_source_asset_reference(raw_source)
        source_text = str(ref.source).strip()
        if not source_text:
            issues.append(
                CompositionPreflightIssue(
                    code="storage_uri_missing",
                    message=f"asset {layer.asset_id!r} has an empty storage URI/source path",
                    asset_id=layer.asset_id,
                    layer_id=layer.layer_id,
                )
            )
            continue

        if ref.status is not None and ref.status.strip().lower() not in READY_ASSET_STATUSES:
            issues.append(
                CompositionPreflightIssue(
                    code="asset_status_not_ready",
                    message=f"asset {layer.asset_id!r} status must be ready before rendering",
                    asset_id=layer.asset_id,
                    layer_id=layer.layer_id,
                )
            )
        if require_content_hash and not _optional_text(ref.content_hash):
            issues.append(
                CompositionPreflightIssue(
                    code="content_hash_missing",
                    message=f"asset {layer.asset_id!r} is missing required content hash metadata",
                    asset_id=layer.asset_id,
                    layer_id=layer.layer_id,
                )
            )
        if ref.media_type is not None:
            actual_media_type = _normalize_media_type(ref.media_type)
            if actual_media_type != layer.media_type:
                issues.append(
                    CompositionPreflightIssue(
                        code="media_type_mismatch",
                        message=(
                            f"asset {layer.asset_id!r} media type {actual_media_type!r} "
                            f"does not match expected {layer.media_type!r}"
                        ),
                        asset_id=layer.asset_id,
                        layer_id=layer.layer_id,
                    )
                )

        issues.extend(
            _validate_source_exists(
                source_text,
                layer=layer,
                storage_client=storage_client,
            )
        )

    return issues


def ensure_composition_preflight(
    manifest: CompositionManifest,
    *,
    asset_sources: Mapping[str, SourceAssetInput],
    storage_client: StorageObjectProbe | None = None,
    require_content_hash: bool = True,
) -> None:
    """Raise a readable preflight error when a composition cannot render safely."""

    issues = validate_composition_manifest(manifest)
    issues.extend(
        validate_source_asset_availability(
            manifest,
            asset_sources=asset_sources,
            storage_client=storage_client,
            require_content_hash=require_content_hash,
        )
    )
    if issues:
        raise CompositionPreflightError(issues)


def coerce_source_asset_reference(value: SourceAssetInput) -> SourceAssetReference:
    """Normalize legacy path/URI values and richer source metadata mappings."""

    if isinstance(value, SourceAssetReference):
        return value
    if isinstance(value, str | PathLike):
        return SourceAssetReference(source=value)

    source = (
        value.get("source")
        or value.get("storage_uri")
        or value.get("uri")
        or value.get("path")
    )
    if source is None:
        source = ""
    return SourceAssetReference(
        source=str(source),
        media_type=_optional_text(value.get("media_type") or value.get("content_type")),
        content_hash=_optional_text(
            value.get("content_hash")
            or value.get("stored_content_hash")
            or value.get("checksum_sha256")
        ),
        status=_optional_text(value.get("status") or value.get("asset_status")),
    )


def source_value(value: SourceAssetInput) -> str | PathLike[str]:
    """Return only the filesystem path or storage URI portion of a source input."""

    return coerce_source_asset_reference(value).source


def _validate_layer_window(
    layer: CompositionLayer,
    *,
    duration: float,
    allowed_media_types: frozenset[str],
    collection_name: str,
    issues: list[CompositionPreflightIssue],
) -> None:
    if layer.media_type not in allowed_media_types:
        issues.append(
            CompositionPreflightIssue(
                code="layer_media_type_invalid",
                message=f"{collection_name} layer {layer.layer_id!r} uses invalid media type",
                asset_id=layer.asset_id,
                layer_id=layer.layer_id,
            )
        )
    if layer.start_time < 0 or layer.end_time < 0:
        issues.append(
            CompositionPreflightIssue(
                code="layer_time_negative",
                message=f"layer {layer.layer_id!r} cannot use negative times",
                asset_id=layer.asset_id,
                layer_id=layer.layer_id,
            )
        )
    if layer.end_time <= layer.start_time:
        issues.append(
            CompositionPreflightIssue(
                code="layer_time_order_invalid",
                message=f"layer {layer.layer_id!r} end_time must be greater than start_time",
                asset_id=layer.asset_id,
                layer_id=layer.layer_id,
            )
        )
    if layer.end_time > duration:
        issues.append(
            CompositionPreflightIssue(
                code="layer_time_outside_duration",
                message=f"layer {layer.layer_id!r} must end within composition duration",
                asset_id=layer.asset_id,
                layer_id=layer.layer_id,
            )
        )


def _validate_source_exists(
    source_text: str,
    *,
    layer: CompositionLayer,
    storage_client: StorageObjectProbe | None,
) -> list[CompositionPreflightIssue]:
    if source_text.startswith("s3://"):
        if storage_client is None:
            return [
                CompositionPreflightIssue(
                    code="storage_probe_missing",
                    message="storage_client is required to verify s3:// source assets",
                    asset_id=layer.asset_id,
                    layer_id=layer.layer_id,
                )
            ]
        try:
            storage_client.head_object(storage_uri=source_text)
        except Exception as exc:
            return [
                CompositionPreflightIssue(
                    code="storage_object_missing",
                    message=(
                        f"asset {layer.asset_id!r} object does not exist or cannot be read: {exc}"
                    ),
                    asset_id=layer.asset_id,
                    layer_id=layer.layer_id,
                )
            ]
        return []

    if "://" in source_text:
        return []

    path = Path(source_text)
    if not path.exists() or not path.is_file():
        return [
            CompositionPreflightIssue(
                code="local_asset_missing",
                message=f"asset {layer.asset_id!r} source file does not exist",
                asset_id=layer.asset_id,
                layer_id=layer.layer_id,
            )
        ]
    return []


def _normalize_media_type(value: str) -> str:
    normalized = value.strip().lower()
    if "/" in normalized:
        family, _, subtype = normalized.partition("/")
        if family == "text":
            return "text"
        if family in {"image", "video", "audio"}:
            return family
        if subtype == "json":
            return "json"
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_preflight_error(issues: Sequence[CompositionPreflightIssue]) -> str:
    joined = "; ".join(issue.message for issue in issues)
    return f"composition preflight failed: {joined}"


__all__ = [
    "CompositionPreflightError",
    "CompositionPreflightIssue",
    "READY_ASSET_STATUSES",
    "SUPPORTED_EXPORT_CONTAINERS",
    "SourceAssetInput",
    "SourceAssetReference",
    "StorageObjectProbe",
    "coerce_source_asset_reference",
    "ensure_composition_preflight",
    "source_value",
    "validate_composition_manifest",
    "validate_source_asset_availability",
]
