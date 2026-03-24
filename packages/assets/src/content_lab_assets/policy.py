"""Policy models and hook protocols for asset reuse decisions."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from content_lab_assets.types import (
    BlockedDecision,
    DecisionPolicyMetadata,
    GenerateDecision,
    ReuseExactDecision,
    ReuseWithTransformDecision,
)


class CooldownPolicy(BaseModel):
    """Optional cooldown configuration for reuse decisions."""

    model_config = ConfigDict(extra="forbid")

    seconds: int | None = Field(default=None, ge=1)


class FamilyReuseCapPolicy(BaseModel):
    """Optional per-family reuse ceiling."""

    model_config = ConfigDict(extra="forbid")

    max_reuses: int | None = Field(default=None, ge=1)


class ReusePolicySettings(BaseModel):
    """Future-safe policy bundle for reuse enforcement."""

    model_config = ConfigDict(extra="forbid")

    cooldown: CooldownPolicy = Field(default_factory=CooldownPolicy)
    family_reuse_cap: FamilyReuseCapPolicy = Field(default_factory=FamilyReuseCapPolicy)


class ReusePolicyContext(BaseModel):
    """Optional policy context passed through phase-1 resolution."""

    model_config = ConfigDict(extra="forbid")

    family_id: str | None = None
    family_reuse_count: int | None = Field(default=None, ge=0)
    last_reused_at: datetime | None = None
    settings: ReusePolicySettings = Field(default_factory=ReusePolicySettings)


def build_decision_policy_metadata(
    context: ReusePolicyContext | None = None,
) -> DecisionPolicyMetadata:
    """Convert a policy context into the stable decision metadata envelope."""

    if context is None:
        return DecisionPolicyMetadata()

    active_rules: list[str] = []
    if context.settings.cooldown.seconds is not None:
        active_rules.append("cooldown")
    if context.settings.family_reuse_cap.max_reuses is not None:
        active_rules.append("family_reuse_cap")

    return DecisionPolicyMetadata(
        family_id=context.family_id,
        family_reuse_count=context.family_reuse_count,
        family_reuse_cap=context.settings.family_reuse_cap.max_reuses,
        cooldown_seconds=context.settings.cooldown.seconds,
        last_reused_at=context.last_reused_at,
        active_rules=active_rules,
    )


@runtime_checkable
class AssetReusePolicyHooks(Protocol):
    """Optional policy extension points layered on top of phase-1 resolution."""

    def on_exact_reuse_candidate(
        self,
        *,
        decision: ReuseExactDecision,
        context: ReusePolicyContext,
    ) -> ReuseWithTransformDecision | BlockedDecision | None: ...

    def on_generate_candidate(
        self,
        *,
        decision: GenerateDecision,
        context: ReusePolicyContext,
    ) -> BlockedDecision | None: ...


class NoopAssetReusePolicyHooks:
    """Default hook implementation that preserves phase-1 behavior."""

    def on_exact_reuse_candidate(
        self,
        *,
        decision: ReuseExactDecision,
        context: ReusePolicyContext,
    ) -> ReuseWithTransformDecision | BlockedDecision | None:
        del decision, context
        return None

    def on_generate_candidate(
        self,
        *,
        decision: GenerateDecision,
        context: ReusePolicyContext,
    ) -> BlockedDecision | None:
        del decision, context
        return None


__all__ = [
    "AssetReusePolicyHooks",
    "CooldownPolicy",
    "FamilyReuseCapPolicy",
    "NoopAssetReusePolicyHooks",
    "ReusePolicyContext",
    "ReusePolicySettings",
    "build_decision_policy_metadata",
]
