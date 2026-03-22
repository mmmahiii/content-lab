"""Asset registry primitives for cataloguing, exact memoisation, and resolution."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from content_lab_core.models import DomainModel
from content_lab_core.types import AssetKind

PHASE1_VIDEO_PROVIDER = "runway"
PHASE1_VIDEO_MODEL = "gen4.5"


class AssetRecord(DomainModel):
    """Metadata record for a catalogued asset."""

    name: str
    kind: AssetKind
    content_hash: str
    storage_uri: str
    size_bytes: int = 0
    tags: list[str] = Field(default_factory=list)


@runtime_checkable
class AssetRegistry(Protocol):
    """Interface for asset catalogue operations."""

    def register(self, record: AssetRecord) -> AssetRecord: ...

    def lookup_by_hash(self, content_hash: str) -> AssetRecord | None: ...


class Phase1ProviderLockError(ValueError):
    """Raised when a request falls outside the locked phase-1 video path."""


class AssetKey(BaseModel):
    """Deterministic exact-match key material for a generation request."""

    model_config = ConfigDict(extra="forbid")

    asset_key: str
    asset_key_hash: str
    canonical_params: dict[str, Any]


class GenerationIntent(BaseModel):
    """Persistable intent envelope for later provider submission."""

    model_config = ConfigDict(extra="forbid")

    task_id: uuid.UUID | None = None
    task_type: str
    task_status: str | None = None
    idempotency_key: str
    asset_class: str
    provider: str
    model: str
    asset_key: str
    asset_key_hash: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AssetResolutionDecisionBase(BaseModel):
    """Shared fields returned by the phase-1 resolver."""

    model_config = ConfigDict(extra="forbid")

    decision: str
    asset_key: str
    asset_key_hash: str
    asset_class: str
    provider: str
    model: str
    canonical_params: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ReuseExactDecision(AssetResolutionDecisionBase):
    """Resolve to an already-registered asset with an identical AssetKey."""

    decision: Literal["reuse_exact"] = "reuse_exact"
    asset_id: uuid.UUID
    storage_uri: str


class GenerateDecision(AssetResolutionDecisionBase):
    """Resolve to a fresh generation-intent task."""

    decision: Literal["generate"] = "generate"
    generation_intent: GenerationIntent


class ReuseWithTransformDecision(AssetResolutionDecisionBase):
    """Reserved later-compatible outcome for deterministic transform reuse."""

    decision: Literal["reuse_with_transform"] = "reuse_with_transform"
    asset_id: uuid.UUID
    reason: str
    transform_recipe: dict[str, Any] = Field(default_factory=dict)


class BlockedDecision(AssetResolutionDecisionBase):
    """Reserved later-compatible outcome for policy or safety blocking."""

    decision: Literal["blocked"] = "blocked"
    reason: str


AssetResolutionDecision = (
    ReuseExactDecision | GenerateDecision | ReuseWithTransformDecision | BlockedDecision
)


def validate_phase1_provider_model(*, provider: str, model: str) -> tuple[str, str]:
    """Validate the locked MVP provider path and return canonical values."""

    normalized_provider = _normalize_identifier(provider)
    normalized_model = _normalize_identifier(model)
    if normalized_provider != PHASE1_VIDEO_PROVIDER or normalized_model != PHASE1_VIDEO_MODEL:
        raise Phase1ProviderLockError(
            "phase-1 asset resolution only supports provider='runway' and model='gen4.5'"
        )
    return normalized_provider, normalized_model


def build_asset_key(
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
) -> AssetKey:
    """Canonicalise supported generation inputs and derive deterministic key material."""

    normalized_provider, normalized_model = validate_phase1_provider_model(
        provider=provider,
        model=model,
    )
    canonical_prompt = _normalize_required_text(prompt, field_name="prompt")
    canonical_asset_class = _normalize_required_text(asset_class, field_name="asset_class").lower()
    canonical_params: dict[str, Any] = {
        "asset_class": canonical_asset_class,
        "provider": normalized_provider,
        "model": normalized_model,
        "prompt": canonical_prompt,
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

    canonical_ratio = _normalize_optional_identifier(ratio)
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

    asset_key = json.dumps(canonical_params, sort_keys=True, separators=(",", ":"))
    asset_key_hash = hashlib.sha256(asset_key.encode("utf-8")).hexdigest()
    return AssetKey(
        asset_key=asset_key,
        asset_key_hash=asset_key_hash,
        canonical_params=canonical_params,
    )


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
    return _normalize_required_text(value, field_name="identifier").lower()


def _normalize_optional_identifier(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    return None if normalized is None else normalized.lower()


def _normalize_number(value: float | int | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _canonicalize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    for key in sorted(value):
        normalized_value = _canonicalize_value(value[key])
        if normalized_value is None:
            continue
        canonical[str(key)] = normalized_value
    return canonical


def _canonicalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        canonical_mapping = _canonicalize_mapping(value)
        return canonical_mapping or None
    if isinstance(value, list | tuple):
        return [_canonicalize_value(item) for item in value]
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
