"""Typed asset-resolution contracts shared across resolver and API layers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PHASE1_GENERATION_TASK_TYPE = "asset.generate"


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


class DecisionPolicyMetadata(BaseModel):
    """Stable policy envelope reserved for later reuse enforcement and QA."""

    model_config = ConfigDict(extra="forbid")

    family_id: str | None = None
    family_reuse_count: int | None = Field(default=None, ge=0)
    family_reuse_cap: int | None = Field(default=None, ge=1)
    cooldown_seconds: int | None = Field(default=None, ge=1)
    last_reused_at: datetime | None = None
    active_rules: list[str] = Field(default_factory=list)


class AssetResolutionDecisionBase(BaseModel):
    """Shared fields returned by the asset resolver."""

    model_config = ConfigDict(extra="forbid")

    decision: str
    asset_key: str
    asset_key_hash: str
    asset_class: str
    provider: str
    model: str
    canonical_params: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    policy: DecisionPolicyMetadata = Field(default_factory=DecisionPolicyMetadata)


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
    """Resolve to a deterministic mutation of an existing asset."""

    decision: Literal["reuse_with_transform"] = "reuse_with_transform"
    asset_id: uuid.UUID
    storage_uri: str | None = None
    reason: str
    reason_code: str
    transform_recipe: dict[str, Any] = Field(default_factory=dict)


class BlockedDecision(AssetResolutionDecisionBase):
    """Resolve to a policy or safety block."""

    decision: Literal["blocked"] = "blocked"
    reason: str
    reason_code: str
    retry_after_seconds: int | None = Field(default=None, ge=1)


AssetResolutionDecision = (
    ReuseExactDecision | GenerateDecision | ReuseWithTransformDecision | BlockedDecision
)


__all__ = [
    "AssetResolutionDecision",
    "AssetResolutionDecisionBase",
    "BlockedDecision",
    "DecisionPolicyMetadata",
    "GenerateDecision",
    "GenerationIntent",
    "PHASE1_GENERATION_TASK_TYPE",
    "ReuseExactDecision",
    "ReuseWithTransformDecision",
]
