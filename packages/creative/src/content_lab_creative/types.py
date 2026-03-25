"""Phase-1 creative director types."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from content_lab_core.types import Platform
from content_lab_creative.persona import PageConstraints, PageMetadata


class CreativeMode(str, Enum):
    """Supported phase-1 creative modes."""

    EXPLOIT = "exploit"
    EXPLORE = "explore"
    MUTATION = "mutation"
    CHAOS = "chaos"


class PolicyModeRatios(BaseModel):
    """Relative weighting for director mode selection."""

    model_config = ConfigDict(extra="forbid")

    exploit: float = Field(default=0.3, ge=0.0, le=1.0)
    explore: float = Field(default=0.4, ge=0.0, le=1.0)
    mutation: float = Field(default=0.2, ge=0.0, le=1.0)
    chaos: float = Field(default=0.1, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _require_unit_sum(self) -> PolicyModeRatios:
        total = self.exploit + self.explore + self.mutation + self.chaos
        if abs(total - 1.0) > 1e-6:
            raise ValueError("mode_ratios must sum to 1.0")
        return self


class PolicyBudgetGuardrails(BaseModel):
    """Budget ceilings kept on the brief for downstream planners."""

    model_config = ConfigDict(extra="forbid")

    per_run_usd_limit: float = Field(default=10.0, ge=0.0, le=100_000.0)
    daily_usd_limit: float = Field(default=40.0, ge=0.0, le=100_000.0)
    monthly_usd_limit: float = Field(default=800.0, ge=0.0, le=1_000_000.0)

    @model_validator(mode="after")
    def _validate_budget_ordering(self) -> PolicyBudgetGuardrails:
        if self.per_run_usd_limit > self.daily_usd_limit:
            raise ValueError("per_run_usd_limit must not exceed daily_usd_limit")
        if self.daily_usd_limit > self.monthly_usd_limit:
            raise ValueError("daily_usd_limit must not exceed monthly_usd_limit")
        return self


class PolicySimilarityThresholds(BaseModel):
    """Similarity thresholds reserved for downstream reuse checks."""

    model_config = ConfigDict(extra="forbid")

    warn_at: float = Field(default=0.72, ge=0.0, le=1.0)
    block_at: float = Field(default=0.88, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_similarity_ordering(self) -> PolicySimilarityThresholds:
        if self.warn_at >= self.block_at:
            raise ValueError("similarity.warn_at must be lower than similarity.block_at")
        return self


class PolicyThresholds(BaseModel):
    """Threshold bundle carried forward to later intelligence work."""

    model_config = ConfigDict(extra="forbid")

    similarity: PolicySimilarityThresholds = Field(default_factory=PolicySimilarityThresholds)
    min_quality_score: float = Field(default=0.55, ge=0.0, le=1.0)


class PolicyStateDocument(BaseModel):
    """Validated policy document used by the creative planner."""

    model_config = ConfigDict(extra="forbid")

    mode_ratios: PolicyModeRatios = Field(default_factory=PolicyModeRatios)
    budget: PolicyBudgetGuardrails = Field(default_factory=PolicyBudgetGuardrails)
    thresholds: PolicyThresholds = Field(default_factory=PolicyThresholds)


class PolicyStatePatch(BaseModel):
    """Optional page-level policy overlay."""

    model_config = ConfigDict(extra="forbid")

    mode_ratios: PolicyModeRatios | None = None
    budget: PolicyBudgetGuardrails | None = None
    thresholds: PolicyThresholds | None = None


class ApplicablePolicyState(BaseModel):
    """Global, page, and merged policy state attached to a planned brief."""

    model_config = ConfigDict(extra="forbid")

    global_policy: PolicyStateDocument
    page_policy: PolicyStatePatch | PolicyStateDocument | None = None
    effective_policy: PolicyStateDocument


class FutureSelectionHooks(BaseModel):
    """Reserved seams for later scoring and ingestion-aware planning."""

    model_config = ConfigDict(extra="forbid")

    scoring_inputs: dict[str, object] = Field(default_factory=dict)
    ingestion_inputs: dict[str, object] = Field(default_factory=dict)


class DirectorSelectionTrace(BaseModel):
    """Deterministic trace of how the phase-1 brief was selected."""

    model_config = ConfigDict(extra="forbid")

    selection_version: Literal["phase_1"] = "phase_1"
    brief_index: int = Field(default=0, ge=0)
    seed_material: str
    seed_bucket: float = Field(ge=0.0, le=1.0)
    selected_mode: CreativeMode
    mode_weights: PolicyModeRatios
    future_hooks: FutureSelectionHooks = Field(default_factory=FutureSelectionHooks)


class DirectorPlanInput(BaseModel):
    """Phase-1 creative director inputs."""

    model_config = ConfigDict(extra="forbid")

    page_name: str = Field(min_length=1, max_length=160)
    page_metadata: PageMetadata = Field(default_factory=PageMetadata)
    global_policy: PolicyStateDocument = Field(default_factory=PolicyStateDocument)
    page_policy: PolicyStatePatch | PolicyStateDocument | None = None
    brief_index: int = Field(default=0, ge=0)
    target_platforms: list[Platform] = Field(default_factory=list)
    duration_seconds: int = Field(default=30, ge=5, le=180)


class PlannedCreativeBrief(BaseModel):
    """Structured phase-1 creative brief output."""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str = ""
    target_platforms: list[Platform] = Field(default_factory=list)
    tone: str = "neutral"
    duration_seconds: int = 30
    tags: list[str] = Field(default_factory=list)
    page_name: str
    page_metadata: PageMetadata = Field(default_factory=PageMetadata)
    persona_label: str | None = None
    audience: str | None = None
    content_pillar: str
    selected_mode: CreativeMode
    narrative_goal: str
    primary_call_to_action: str | None = None
    constraints: PageConstraints = Field(default_factory=PageConstraints)
    policy: ApplicablePolicyState
    selection_trace: DirectorSelectionTrace

    @property
    def is_short_form(self) -> bool:
        return self.duration_seconds <= 60
