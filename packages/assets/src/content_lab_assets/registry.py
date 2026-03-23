"""Asset registry primitives for cataloguing, exact memoisation, and resolution."""

from __future__ import annotations

import uuid
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

__all__ = [
    "AssetKey",
    "AssetRecord",
    "AssetRegistry",
    "AssetResolutionDecision",
    "BlockedDecision",
    "GenerateDecision",
    "GenerationIntent",
    "Phase1ProviderLockError",
    "ReuseExactDecision",
    "ReuseWithTransformDecision",
    "build_asset_key",
    "validate_phase1_provider_model",
]
