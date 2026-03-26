"""Policy models and hook protocols for asset reuse decisions."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class RepetitionThresholdPolicy(BaseModel):
    """Optional warn/fail thresholds for phase-1 repetition checks."""

    model_config = ConfigDict(extra="forbid")

    exact_reuse_warn_at: int | None = Field(default=None, ge=1)
    exact_reuse_fail_at: int | None = Field(default=None, ge=1)
    family_reuse_warn_at: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_ordering(self) -> RepetitionThresholdPolicy:
        if (
            self.exact_reuse_warn_at is not None
            and self.exact_reuse_fail_at is not None
            and self.exact_reuse_warn_at >= self.exact_reuse_fail_at
        ):
            raise ValueError("repetition.exact_reuse_warn_at must be lower than fail_at")
        return self


class ReusePolicySettings(BaseModel):
    """Future-safe policy bundle for reuse enforcement."""

    model_config = ConfigDict(extra="forbid")

    cooldown: CooldownPolicy = Field(default_factory=CooldownPolicy)
    family_reuse_cap: FamilyReuseCapPolicy = Field(default_factory=FamilyReuseCapPolicy)
    repetition: RepetitionThresholdPolicy = Field(default_factory=RepetitionThresholdPolicy)


class ReusePolicyContext(BaseModel):
    """Optional policy context passed through phase-1 resolution."""

    model_config = ConfigDict(extra="forbid")

    family_id: str | None = None
    exact_reuse_count: int | None = Field(default=None, ge=0)
    family_reuse_count: int | None = Field(default=None, ge=0)
    last_reused_at: datetime | None = None
    last_exact_reused_at: datetime | None = None
    last_family_reused_at: datetime | None = None
    settings: ReusePolicySettings = Field(default_factory=ReusePolicySettings)

    @model_validator(mode="after")
    def _sync_family_recency_aliases(self) -> ReusePolicyContext:
        if self.last_family_reused_at is None and self.last_reused_at is not None:
            self.last_family_reused_at = self.last_reused_at
        if self.last_reused_at is None and self.last_family_reused_at is not None:
            self.last_reused_at = self.last_family_reused_at
        return self


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
    if _has_repetition_thresholds(context.settings.repetition):
        active_rules.append("repetition")

    return DecisionPolicyMetadata(
        family_id=context.family_id,
        family_reuse_count=context.family_reuse_count,
        family_reuse_cap=context.settings.family_reuse_cap.max_reuses,
        cooldown_seconds=context.settings.cooldown.seconds,
        last_reused_at=context.last_family_reused_at,
        active_rules=active_rules,
    )


def build_repetition_gate_payload(
    context: ReusePolicyContext | None = None,
) -> dict[str, object]:
    """Build a phase-1 repetition payload that downstream QA can consume directly."""

    normalized_context = context or ReusePolicyContext()
    return {
        "family_id": normalized_context.family_id,
        "history": {
            "exact_reuse_count": normalized_context.exact_reuse_count or 0,
            "family_reuse_count": normalized_context.family_reuse_count or 0,
            "last_exact_reused_at": normalized_context.last_exact_reused_at,
            "last_family_reused_at": normalized_context.last_family_reused_at,
        },
        "policy": {
            "cooldown_seconds": normalized_context.settings.cooldown.seconds,
            "family_reuse_cap": normalized_context.settings.family_reuse_cap.max_reuses,
            "exact_reuse_warn_at": normalized_context.settings.repetition.exact_reuse_warn_at,
            "exact_reuse_fail_at": normalized_context.settings.repetition.exact_reuse_fail_at,
            "family_reuse_warn_at": normalized_context.settings.repetition.family_reuse_warn_at,
        },
    }


def _has_repetition_thresholds(thresholds: RepetitionThresholdPolicy) -> bool:
    return any(
        value is not None
        for value in (
            thresholds.exact_reuse_warn_at,
            thresholds.exact_reuse_fail_at,
            thresholds.family_reuse_warn_at,
        )
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
    "RepetitionThresholdPolicy",
    "ReusePolicyContext",
    "ReusePolicySettings",
    "build_repetition_gate_payload",
    "build_decision_policy_metadata",
]
