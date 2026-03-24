"""Deterministic canonicalisation helpers for Runway gen4.5 generation inputs.

The canonical payload shape is the exact material hashed into an AssetKey.
For phase-1 Runway ``gen4.5`` generation we normalise inputs as follows:

- required text fields are trimmed and internal whitespace is collapsed;
- optional blank strings are omitted from the payload;
- provider/model, aspect ratio, init-image hashes, and reference IDs are lower-cased;
- aspect ratios such as ``9 : 16`` and ``9x16`` canonicalise to ``9:16``;
- integral floats canonicalise to integers so ``6`` and ``6.0`` hash identically;
- motion parameter mappings are canonicalised recursively with stable key ordering.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, NotRequired, TypedDict

_ASPECT_RATIO_PATTERN = re.compile(r"^\s*(\d+)\s*(?::|x|/)\s*(\d+)\s*$", re.IGNORECASE)


class RunwayGen45AssetKeyPayload(TypedDict):
    """Canonical AssetKey payload for a Runway gen4.5 generation request."""

    asset_class: str
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


def canonicalise_runway_gen45_generation(
    *,
    asset_class: str,
    provider: str,
    model: str,
    prompt: str,
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

    canonical_params: RunwayGen45AssetKeyPayload = {
        "asset_class": _normalize_required_text(asset_class, field_name="asset_class").lower(),
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


def _canonicalize_reference_asset_ids(
    value: Sequence[uuid.UUID | str],
) -> list[str]:
    return sorted({str(item).strip().lower() for item in value})
