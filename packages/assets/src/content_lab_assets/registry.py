"""Asset registry primitives for cataloguing, exact memoisation, and resolution."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from content_lab_assets.asset_key import (
    AssetKey,
    Phase1ProviderLockError,
    build_asset_key,
    validate_phase1_provider_model,
)
from content_lab_core.models import DomainModel
from content_lab_core.types import AssetKind

PHASE1_GENERATION_TASK_TYPE = "asset.generate"
PHASE1_READY_ASSET_STATUSES = frozenset({"active", "ready"})


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


class GenerationIntent(BaseModel):
    """Persistable intent envelope for later provider submission."""

    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    asset_status: str
    storage_uri: str
    task_id: uuid.UUID | None = None
    task_type: str = PHASE1_GENERATION_TASK_TYPE
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


class RegistryAsset(BaseModel):
    """Asset row fields required by the shared phase-1 resolver."""

    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    org_id: uuid.UUID
    asset_class: str
    status: str
    source: str
    storage_uri: str
    asset_key: str | None = None
    asset_key_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegistryAssetGenParams(BaseModel):
    """Canonical parameter history fields required by the shared resolver."""

    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    seq: int
    asset_key_hash: str
    canonical_params: dict[str, Any] = Field(default_factory=dict)


class RegistryGenerationIntentRecord(BaseModel):
    """Persisted staged-asset intent state returned by store adapters."""

    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    org_id: uuid.UUID
    asset_class: str
    status: str
    source: str
    storage_uri: str
    asset_key: str
    asset_key_hash: str
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    canonical_params: dict[str, Any] = Field(default_factory=dict)
    created: bool = False


@runtime_checkable
class Phase1AssetRegistryStore(Protocol):
    """Persistence boundary for phase-1 exact reuse and staged intent creation."""

    def get_asset_by_key_hash(
        self,
        *,
        org_id: uuid.UUID,
        asset_key_hash: str,
    ) -> RegistryAsset | None: ...

    def get_generation_params(
        self,
        *,
        asset_id: uuid.UUID,
        asset_key_hash: str,
    ) -> RegistryAssetGenParams | None: ...

    def ensure_generation_intent(
        self,
        *,
        org_id: uuid.UUID,
        asset_key: AssetKey,
        payload: Mapping[str, Any],
    ) -> RegistryGenerationIntentRecord: ...


def build_generation_idempotency_key(*, asset_key_hash: str) -> str:
    """Build the canonical phase-1 idempotency key for generated-asset intents."""

    normalized_hash = _normalize_required_text(asset_key_hash, field_name="asset_key_hash").lower()
    key = f"{PHASE1_GENERATION_TASK_TYPE}:{normalized_hash}"
    if len(key) > 256:
        raise ValueError("generation idempotency key must be at most 256 characters")
    return key


def is_ready_asset_status(status: str) -> bool:
    """Return whether an asset status is reusable as a ready phase-1 asset."""

    return (
        _normalize_required_text(status, field_name="status").lower()
        in PHASE1_READY_ASSET_STATUSES
    )


def build_generation_payload(
    *,
    asset_key: AssetKey,
    request_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable generation payload for later provider submission."""

    canonical_params = dict(asset_key.canonical_params)
    return {
        "resolution": "generate",
        "request": dict(request_payload or {}),
        "asset_key": asset_key.asset_key,
        "asset_key_hash": asset_key.asset_key_hash,
        "canonical_params": canonical_params,
        "provider_submission": {
            "provider": canonical_params["provider"],
            "model": canonical_params["model"],
            "asset_class": canonical_params["asset_class"],
        },
        "provenance": {
            "source": "asset_registry.resolve",
            "phase": "phase1_exact_reuse",
            "reference_asset_ids": canonical_params.get("reference_asset_ids", []),
            "init_image_hash": canonical_params.get("init_image_hash"),
        },
    }


def resolve_phase1_asset(
    store: Phase1AssetRegistryStore,
    *,
    org_id: uuid.UUID,
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
    request_payload: Mapping[str, Any] | None = None,
) -> AssetResolutionDecision:
    """Resolve a phase-1 generation request through exact reuse or staged generation."""

    asset_key = build_asset_key(
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
    existing_asset = store.get_asset_by_key_hash(
        org_id=org_id,
        asset_key_hash=asset_key.asset_key_hash,
    )
    if existing_asset is not None and is_ready_asset_status(existing_asset.status):
        gen_params = store.get_generation_params(
            asset_id=existing_asset.asset_id,
            asset_key_hash=asset_key.asset_key_hash,
        )
        return _reuse_exact_decision(existing_asset, asset_key=asset_key, gen_params=gen_params)

    payload = build_generation_payload(asset_key=asset_key, request_payload=request_payload)
    intent = store.ensure_generation_intent(
        org_id=org_id,
        asset_key=asset_key,
        payload=payload,
    )
    return _generate_decision(intent, asset_key=asset_key)


def _reuse_exact_decision(
    asset: RegistryAsset,
    *,
    asset_key: AssetKey,
    gen_params: RegistryAssetGenParams | None,
) -> ReuseExactDecision:
    return ReuseExactDecision(
        asset_id=asset.asset_id,
        asset_class=asset.asset_class,
        storage_uri=asset.storage_uri,
        asset_key=asset_key.asset_key,
        asset_key_hash=asset_key.asset_key_hash,
        provider=asset_key.canonical_params["provider"],
        model=asset_key.canonical_params["model"],
        canonical_params=(
            asset_key.canonical_params if gen_params is None else dict(gen_params.canonical_params)
        ),
        provenance={
            "source": "asset_registry",
            "resolution": "exact_memoisation",
            "matched_via": "asset_key_hash",
            "asset_status": asset.status,
            "asset_gen_param_seq": None if gen_params is None else gen_params.seq,
        },
    )


def _generate_decision(
    intent: RegistryGenerationIntentRecord,
    *,
    asset_key: AssetKey,
) -> GenerateDecision:
    generation_intent = GenerationIntent(
        asset_id=intent.asset_id,
        asset_status=intent.status,
        storage_uri=intent.storage_uri,
        idempotency_key=intent.idempotency_key,
        asset_class=intent.asset_class,
        provider=asset_key.canonical_params["provider"],
        model=asset_key.canonical_params["model"],
        asset_key=asset_key.asset_key,
        asset_key_hash=asset_key.asset_key_hash,
        payload=dict(intent.payload),
    )
    return GenerateDecision(
        asset_class=asset_key.canonical_params["asset_class"],
        asset_key=asset_key.asset_key,
        asset_key_hash=asset_key.asset_key_hash,
        provider=asset_key.canonical_params["provider"],
        model=asset_key.canonical_params["model"],
        canonical_params=asset_key.canonical_params,
        generation_intent=generation_intent,
        provenance={
            "source": "asset_registry",
            "resolution": "generate",
            "asset_id": str(intent.asset_id),
            "asset_status": intent.status,
        },
    )


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


__all__ = [
    "AssetKey",
    "AssetRecord",
    "AssetRegistry",
    "AssetResolutionDecision",
    "BlockedDecision",
    "GenerateDecision",
    "GenerationIntent",
    "PHASE1_GENERATION_TASK_TYPE",
    "PHASE1_READY_ASSET_STATUSES",
    "Phase1AssetRegistryStore",
    "Phase1ProviderLockError",
    "RegistryAsset",
    "RegistryAssetGenParams",
    "RegistryGenerationIntentRecord",
    "ReuseExactDecision",
    "ReuseWithTransformDecision",
    "build_asset_key",
    "build_generation_idempotency_key",
    "build_generation_payload",
    "is_ready_asset_status",
    "resolve_phase1_asset",
    "validate_phase1_provider_model",
]
