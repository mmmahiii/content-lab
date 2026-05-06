"""AssetKey models and hashing for phase-1 Runway gen4.5 generation."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from content_lab_assets.canonicalise import (
    canonicalise_audio,
    canonicalise_derived_transform,
    canonicalise_final_render,
    canonicalise_overlay_text,
    canonicalise_runway_gen45_generation,
    normalize_identifier,
    serialise_canonical_payload,
)
from content_lab_assets.types import AssetKind, AssetSource, MediaType

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
) -> AssetKey:
    """Canonicalise supported generation inputs and derive deterministic SHA-256 key material.

    The canonical payload includes ``asset_kind``, ``media_type``, and
    ``asset_source`` (KEY-001/KEY-002) so different component roles never
    collide on AssetKey, even with identical prompts and provider params.
    """

    validate_phase1_provider_model(provider=provider, model=model)
    canonical_params = canonicalise_runway_gen45_generation(
        asset_class=asset_class,
        asset_kind=asset_kind,
        media_type=media_type,
        asset_source=asset_source,
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
    return _build_key_from_canonical_params(canonical_params)


def build_derived_asset_key(
    *,
    asset_kind: AssetKind | str,
    media_type: MediaType | str | None = None,
    source_asset_id: uuid.UUID | str | None = None,
    source_content_hash: str | None = None,
    transform_recipe: Mapping[str, Any],
    transform_recipe_version: str,
    output_parameters: Mapping[str, Any],
) -> AssetKey:
    """Build an AssetKey for a deterministic transform of an existing asset."""

    canonical_params = canonicalise_derived_transform(
        asset_kind=asset_kind,
        media_type=media_type,
        source_asset_id=source_asset_id,
        source_content_hash=source_content_hash,
        transform_recipe=transform_recipe,
        transform_recipe_version=transform_recipe_version,
        output_parameters=output_parameters,
    )
    return _build_key_from_canonical_params(canonical_params)


def build_overlay_text_asset_key(
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
) -> AssetKey:
    """Build an AssetKey for reusable hook text, captions, and overlay plans."""

    canonical_params = canonicalise_overlay_text(
        asset_kind=asset_kind,
        canonical_text=canonical_text,
        timing=timing,
        layout=layout,
        safe_area=safe_area,
        template_version=template_version,
        style=style,
        media_type=media_type,
        asset_source=asset_source,
    )
    return _build_key_from_canonical_params(canonical_params)


def build_audio_asset_key(
    *,
    asset_kind: AssetKind | str,
    audio_identity: Any,
    trim_range: Any,
    volume: Any,
    normalisation: Any,
    looping: Any,
    media_type: MediaType | str | None = None,
    asset_source: AssetSource | str = AssetSource.DERIVED,
) -> AssetKey:
    """Build an AssetKey for a reusable audio component."""

    canonical_params = canonicalise_audio(
        asset_kind=asset_kind,
        audio_identity=audio_identity,
        trim_range=trim_range,
        volume=volume,
        normalisation=normalisation,
        looping=looping,
        media_type=media_type,
        asset_source=asset_source,
    )
    return _build_key_from_canonical_params(canonical_params)


def build_final_render_asset_key(
    *,
    ordered_source_asset_ids_or_hashes: Sequence[uuid.UUID | str],
    composition_manifest_hash: str,
    edit_template_version: str,
    export_preset: Any,
    render_parameters: Mapping[str, Any],
    asset_kind: AssetKind | str = AssetKind.FINAL_RENDER,
    media_type: MediaType | str | None = None,
    asset_source: AssetSource | str = AssetSource.PACKAGE_OUTPUT,
) -> AssetKey:
    """Build an AssetKey for a deterministic final render output."""

    canonical_params = canonicalise_final_render(
        ordered_source_asset_ids_or_hashes=ordered_source_asset_ids_or_hashes,
        composition_manifest_hash=composition_manifest_hash,
        edit_template_version=edit_template_version,
        export_preset=export_preset,
        render_parameters=render_parameters,
        asset_kind=asset_kind,
        media_type=media_type,
        asset_source=asset_source,
    )
    return _build_key_from_canonical_params(canonical_params)


def _build_key_from_canonical_params(canonical_params: Mapping[str, Any]) -> AssetKey:
    asset_key = serialise_canonical_payload(canonical_params)
    return AssetKey(
        asset_key=asset_key,
        asset_key_hash=hashlib.sha256(asset_key.encode("utf-8")).hexdigest(),
        canonical_params=dict(canonical_params),
    )
