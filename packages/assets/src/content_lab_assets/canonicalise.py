"""Deterministic canonicalisation helpers for Runway gen4.5 generation inputs.

The canonical payload shape is the exact material hashed into an AssetKey.
For phase-1 Runway ``gen4.5`` generation we normalise inputs as follows:

- required text fields are trimmed and internal whitespace is collapsed;
- optional blank strings are omitted from the payload;
- provider/model, aspect ratio, init-image hashes, and reference IDs are lower-cased;
- aspect ratios such as ``9 : 16`` and ``9x16`` canonicalise to ``9:16``;
- integral floats canonicalise to integers so ``6`` and ``6.0`` hash identically;
- motion parameter mappings are canonicalised recursively with stable key ordering.

KEY-001 / KEY-002 (composable asset registry) extend the payload with
``asset_kind``, ``media_type``, and ``asset_source`` so that different output
roles (background_image, object_image, final_render, hook_text, ...) hash to
distinct AssetKeys even when the prompt and provider parameters match.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, NotRequired, TypedDict

from content_lab_assets.types import (
    AssetKind,
    AssetSource,
    MediaType,
    infer_media_type_for_asset_kind,
    validate_asset_kind_media_type,
)

_ASPECT_RATIO_PATTERN = re.compile(r"^\s*(\d+)\s*(?::|x|/)\s*(\d+)\s*$", re.IGNORECASE)


class RunwayGen45AssetKeyPayload(TypedDict):
    """Canonical AssetKey payload for a Runway gen4.5 generation request."""

    asset_class: str
    asset_kind: str
    media_type: str
    asset_source: str
    provider: str
    model: str
    prompt: str
    negative_prompt: NotRequired[str]
    seed: NotRequired[int]
    duration_seconds: NotRequired[int | float]
    fps: NotRequired[int]
    ratio: NotRequired[str]
    motion: NotRequired[dict[str, Any]]
    init_image_hash: NotRequired[str]
    reference_asset_ids: NotRequired[list[str]]


class DerivedTransformAssetKeyPayload(TypedDict):
    """Canonical AssetKey payload for deterministic derived assets."""

    asset_kind: str
    media_type: str
    asset_source: str
    source_asset_id: NotRequired[str]
    source_content_hash: NotRequired[str]
    transform_recipe: dict[str, Any]
    transform_recipe_version: str
    output_parameters: dict[str, Any]


class OverlayTextAssetKeyPayload(TypedDict):
    """Canonical AssetKey payload for text and overlay creative components."""

    asset_kind: str
    media_type: str
    asset_source: str
    canonical_text: str
    timing: dict[str, Any]
    layout: dict[str, Any]
    safe_area: dict[str, Any]
    template_version: str
    style: dict[str, Any]


class AudioAssetKeyPayload(TypedDict):
    """Canonical AssetKey payload for reusable audio components."""

    asset_kind: str
    media_type: str
    asset_source: str
    audio_identity: Any
    trim_range: Any
    volume: Any
    normalisation: Any
    looping: Any


class FinalRenderAssetKeyPayload(TypedDict):
    """Canonical AssetKey payload for deterministic final render outputs."""

    asset_kind: str
    media_type: str
    asset_source: str
    ordered_source_asset_ids_or_hashes: list[str]
    composition_manifest_hash: str
    edit_template_version: str
    export_preset: Any
    render_parameters: dict[str, Any]


def canonicalise_runway_gen45_generation(
    *,
    asset_class: str,
    provider: str,
    model: str,
    prompt: str,
    asset_kind: AssetKind | str = AssetKind.GENERATED_CLIP,
    media_type: MediaType | str | None = None,
    asset_source: AssetSource | str = AssetSource.GENERATED,
    negative_prompt: str | None = None,
    seed: int | None = None,
    duration_seconds: float | int | None = None,
    fps: int | None = None,
    ratio: str | None = None,
    motion: Mapping[str, Any] | None = None,
    init_image_hash: str | None = None,
    reference_asset_ids: Sequence[uuid.UUID | str] | None = None,
) -> RunwayGen45AssetKeyPayload:
    """Return the canonical payload used for exact-match AssetKey hashing."""

    normalized_asset_kind = AssetKind(asset_kind)
    normalized_media_type = (
        infer_media_type_for_asset_kind(normalized_asset_kind)
        if media_type is None
        else validate_asset_kind_media_type(
            asset_kind=normalized_asset_kind,
            media_type=media_type,
        )
    )
    normalized_asset_source = AssetSource(asset_source)

    canonical_params: RunwayGen45AssetKeyPayload = {
        "asset_class": _normalize_required_text(asset_class, field_name="asset_class").lower(),
        "asset_kind": normalized_asset_kind.value,
        "media_type": normalized_media_type.value,
        "asset_source": normalized_asset_source.value,
        "provider": _normalize_identifier(provider),
        "model": _normalize_identifier(model),
        "prompt": _normalize_required_text(prompt, field_name="prompt"),
    }

    canonical_negative_prompt = _normalize_optional_text(negative_prompt)
    if canonical_negative_prompt is not None:
        canonical_params["negative_prompt"] = canonical_negative_prompt

    if seed is not None:
        canonical_params["seed"] = seed

    canonical_duration_seconds = _normalize_number(duration_seconds)
    if canonical_duration_seconds is not None:
        canonical_params["duration_seconds"] = canonical_duration_seconds

    if fps is not None:
        canonical_params["fps"] = fps

    canonical_ratio = _normalize_ratio(ratio)
    if canonical_ratio is not None:
        canonical_params["ratio"] = canonical_ratio

    canonical_motion = _canonicalize_mapping(motion or {})
    if canonical_motion:
        canonical_params["motion"] = canonical_motion

    canonical_init_image_hash = _normalize_optional_identifier(init_image_hash)
    if canonical_init_image_hash is not None:
        canonical_params["init_image_hash"] = canonical_init_image_hash

    canonical_reference_asset_ids = _canonicalize_reference_asset_ids(reference_asset_ids or [])
    if canonical_reference_asset_ids:
        canonical_params["reference_asset_ids"] = canonical_reference_asset_ids

    return canonical_params


def canonicalise_derived_transform(
    *,
    asset_kind: AssetKind | str,
    media_type: MediaType | str | None = None,
    source_asset_id: uuid.UUID | str | None = None,
    source_content_hash: str | None = None,
    transform_recipe: Mapping[str, Any],
    transform_recipe_version: str,
    output_parameters: Mapping[str, Any],
) -> DerivedTransformAssetKeyPayload:
    """Return canonical key material for reproducible transform outputs."""

    normalized_asset_kind, normalized_media_type = _normalize_asset_kind_media_type(
        asset_kind=asset_kind,
        media_type=media_type,
    )
    canonical_source_asset_id = _normalize_optional_identifier(
        None if source_asset_id is None else str(source_asset_id)
    )
    canonical_source_content_hash = _normalize_optional_identifier(source_content_hash)
    if canonical_source_asset_id is None and canonical_source_content_hash is None:
        raise ValueError("source_asset_id or source_content_hash is required")

    canonical_params: DerivedTransformAssetKeyPayload = {
        "asset_kind": normalized_asset_kind.value,
        "media_type": normalized_media_type.value,
        "asset_source": AssetSource.DERIVED.value,
        "transform_recipe": _canonicalize_mapping(transform_recipe),
        "transform_recipe_version": _normalize_required_text(
            transform_recipe_version,
            field_name="transform_recipe_version",
        ),
        "output_parameters": _canonicalize_mapping(output_parameters),
    }
    if canonical_source_asset_id is not None:
        canonical_params["source_asset_id"] = canonical_source_asset_id
    if canonical_source_content_hash is not None:
        canonical_params["source_content_hash"] = canonical_source_content_hash
    return canonical_params


def canonicalise_overlay_text(
    *,
    asset_kind: AssetKind | str,
    canonical_text: str,
    timing: Mapping[str, Any],
    layout: Mapping[str, Any],
    safe_area: Mapping[str, Any],
    template_version: str,
    style: Mapping[str, Any],
    media_type: MediaType | str | None = None,
    asset_source: AssetSource | str = AssetSource.MANUAL_TEMPLATE,
) -> OverlayTextAssetKeyPayload:
    """Return canonical key material for hook text, captions, and overlay plans."""

    normalized_asset_kind, normalized_media_type = _normalize_asset_kind_media_type(
        asset_kind=asset_kind,
        media_type=media_type,
    )
    normalized_asset_source = AssetSource(asset_source)
    return {
        "asset_kind": normalized_asset_kind.value,
        "media_type": normalized_media_type.value,
        "asset_source": normalized_asset_source.value,
        "canonical_text": _normalize_required_text(canonical_text, field_name="canonical_text"),
        "timing": _canonicalize_mapping(timing),
        "layout": _canonicalize_mapping(layout),
        "safe_area": _canonicalize_mapping(safe_area),
        "template_version": _normalize_required_text(
            template_version,
            field_name="template_version",
        ),
        "style": _canonicalize_mapping(style),
    }


def canonicalise_audio(
    *,
    asset_kind: AssetKind | str,
    audio_identity: Any,
    trim_range: Any,
    volume: Any,
    normalisation: Any,
    looping: Any,
    media_type: MediaType | str | None = None,
    asset_source: AssetSource | str = AssetSource.DERIVED,
) -> AudioAssetKeyPayload:
    """Return canonical key material for reusable audio assets."""

    normalized_asset_kind, normalized_media_type = _normalize_asset_kind_media_type(
        asset_kind=asset_kind,
        media_type=media_type,
    )
    normalized_asset_source = AssetSource(asset_source)
    return {
        "asset_kind": normalized_asset_kind.value,
        "media_type": normalized_media_type.value,
        "asset_source": normalized_asset_source.value,
        "audio_identity": _canonicalize_required_value(
            audio_identity,
            field_name="audio_identity",
        ),
        "trim_range": _canonicalize_required_value(trim_range, field_name="trim_range"),
        "volume": _canonicalize_required_value(volume, field_name="volume"),
        "normalisation": _canonicalize_required_value(
            normalisation,
            field_name="normalisation",
        ),
        "looping": _canonicalize_required_value(looping, field_name="looping"),
    }


def canonicalise_final_render(
    *,
    ordered_source_asset_ids_or_hashes: Sequence[uuid.UUID | str],
    composition_manifest_hash: str,
    edit_template_version: str,
    export_preset: Any,
    render_parameters: Mapping[str, Any],
    asset_kind: AssetKind | str = AssetKind.FINAL_RENDER,
    media_type: MediaType | str | None = None,
    asset_source: AssetSource | str = AssetSource.PACKAGE_OUTPUT,
) -> FinalRenderAssetKeyPayload:
    """Return canonical key material for deterministic final render outputs."""

    normalized_asset_kind, normalized_media_type = _normalize_asset_kind_media_type(
        asset_kind=asset_kind,
        media_type=media_type,
    )
    normalized_asset_source = AssetSource(asset_source)
    ordered_sources = _canonicalize_ordered_asset_ids_or_hashes(
        ordered_source_asset_ids_or_hashes,
    )
    if not ordered_sources:
        raise ValueError("ordered_source_asset_ids_or_hashes must not be empty")
    return {
        "asset_kind": normalized_asset_kind.value,
        "media_type": normalized_media_type.value,
        "asset_source": normalized_asset_source.value,
        "ordered_source_asset_ids_or_hashes": ordered_sources,
        "composition_manifest_hash": _normalize_required_text(
            composition_manifest_hash,
            field_name="composition_manifest_hash",
        ).lower(),
        "edit_template_version": _normalize_required_text(
            edit_template_version,
            field_name="edit_template_version",
        ),
        "export_preset": _canonicalize_required_value(
            export_preset,
            field_name="export_preset",
        ),
        "render_parameters": _canonicalize_mapping(render_parameters),
    }


def serialise_canonical_payload(payload: Mapping[str, Any]) -> str:
    """Serialise canonical payloads with stable key ordering and no extra whitespace."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def normalize_identifier(value: str, *, field_name: str = "identifier") -> str:
    """Normalise identifier-like inputs via whitespace collapse plus lower-casing."""

    return _normalize_required_text(value, field_name=field_name).lower()


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize_text(value)
    return normalized or None


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def _normalize_identifier(value: str) -> str:
    return normalize_identifier(value)


def _normalize_optional_identifier(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    return None if normalized is None else normalized.lower()


def _normalize_ratio(value: str | None) -> str | None:
    normalized = _normalize_optional_identifier(value)
    if normalized is None:
        return None

    match = _ASPECT_RATIO_PATTERN.match(normalized)
    if match is None:
        return normalized

    width, height = match.groups()
    return f"{int(width)}:{int(height)}"


def _normalize_number(value: float | int | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _canonicalize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    for key, raw_value in sorted(value.items(), key=lambda item: str(item[0])):
        normalized_key = _normalize_text(str(key))
        if not normalized_key:
            continue
        normalized_value = _canonicalize_value(raw_value)
        if normalized_value is None:
            continue
        canonical[normalized_key] = normalized_value
    return canonical


def _canonicalize_sequence(value: Sequence[Any]) -> list[Any]:
    canonical_items: list[Any] = []
    for item in value:
        normalized_item = _canonicalize_value(item)
        if normalized_item is None:
            continue
        canonical_items.append(normalized_item)
    return canonical_items


def _canonicalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        canonical_mapping = _canonicalize_mapping(value)
        return canonical_mapping or None
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        canonical_sequence = _canonicalize_sequence(value)
        return canonical_sequence or None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        normalized = _normalize_text(value)
        return normalized or None
    if isinstance(value, float):
        return _normalize_number(value)
    return value


def _canonicalize_required_value(value: Any, *, field_name: str) -> Any:
    normalized = _canonicalize_value(value)
    if normalized is None:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _normalize_asset_kind_media_type(
    *,
    asset_kind: AssetKind | str,
    media_type: MediaType | str | None,
) -> tuple[AssetKind, MediaType]:
    normalized_asset_kind = AssetKind(asset_kind)
    normalized_media_type = (
        infer_media_type_for_asset_kind(normalized_asset_kind)
        if media_type is None
        else validate_asset_kind_media_type(
            asset_kind=normalized_asset_kind,
            media_type=media_type,
        )
    )
    return normalized_asset_kind, normalized_media_type


def _canonicalize_reference_asset_ids(
    value: Sequence[uuid.UUID | str],
) -> list[str]:
    return sorted({str(item).strip().lower() for item in value})


def _canonicalize_ordered_asset_ids_or_hashes(
    value: Sequence[uuid.UUID | str],
) -> list[str]:
    canonical_items: list[str] = []
    for item in value:
        normalized = _normalize_optional_identifier(str(item))
        if normalized is not None:
            canonical_items.append(normalized)
    return canonical_items
