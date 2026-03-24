"""AssetKey models and hashing for phase-1 Runway gen4.5 generation."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from content_lab_assets.canonicalise import (
    canonicalise_runway_gen45_generation,
    normalize_identifier,
    serialise_canonical_payload,
)

PHASE1_VIDEO_PROVIDER = "runway"
PHASE1_VIDEO_MODEL = "gen4.5"


class Phase1ProviderLockError(ValueError):
    """Raised when a request falls outside the locked phase-1 video path."""


class AssetKey(BaseModel):
    """Deterministic exact-match key material for a generation request."""

    model_config = ConfigDict(extra="forbid")

    asset_key: str
    asset_key_hash: str
    canonical_params: dict[str, Any]


def validate_phase1_provider_model(*, provider: str, model: str) -> tuple[str, str]:
    """Validate the locked MVP provider path and return canonical provider/model values."""

    normalized_provider = normalize_identifier(provider)
    normalized_model = normalize_identifier(model)
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
    """Canonicalise supported generation inputs and derive deterministic SHA-256 key material."""

    validate_phase1_provider_model(provider=provider, model=model)
    canonical_params = canonicalise_runway_gen45_generation(
        asset_class=asset_class,
        provider=provider,
        model=model,
        prompt=prompt,
        negative_prompt=negative_prompt,
        seed=seed,
        duration_seconds=duration_seconds,
        fps=fps,
        ratio=ratio,
        motion=motion,
        init_image_hash=init_image_hash,
        reference_asset_ids=reference_asset_ids,
    )
    asset_key = serialise_canonical_payload(canonical_params)
    asset_key_hash = hashlib.sha256(asset_key.encode("utf-8")).hexdigest()
    return AssetKey(
        asset_key=asset_key,
        asset_key_hash=asset_key_hash,
        canonical_params=dict(canonical_params),
    )
