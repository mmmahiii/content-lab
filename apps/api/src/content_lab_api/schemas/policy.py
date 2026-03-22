"""Policy state schemas and validation helpers."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyScopeType(str, enum.Enum):
    """Supported policy scopes in the phase-1 architecture."""

    GLOBAL = "global"
    PAGE = "page"
    NICHE = "niche"


class PolicyModeRatios(BaseModel):
    """Relative weighting for concept-generation modes."""

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
    """Budget ceilings used to keep automated generation bounded."""

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
    """Similarity bounds used for warnings and hard blocks."""

    model_config = ConfigDict(extra="forbid")

    warn_at: float = Field(default=0.72, ge=0.0, le=1.0)
    block_at: float = Field(default=0.88, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_similarity_ordering(self) -> PolicySimilarityThresholds:
        if self.warn_at >= self.block_at:
            raise ValueError("similarity.warn_at must be lower than similarity.block_at")
        return self


class PolicyThresholds(BaseModel):
    """Threshold bundle for reuse and quality guardrails."""

    model_config = ConfigDict(extra="forbid")

    similarity: PolicySimilarityThresholds = Field(default_factory=PolicySimilarityThresholds)
    min_quality_score: float = Field(default=0.55, ge=0.0, le=1.0)


class PolicyStateDocument(BaseModel):
    """Validated policy JSON stored inside policy_state rows."""

    model_config = ConfigDict(extra="forbid")

    mode_ratios: PolicyModeRatios = Field(default_factory=PolicyModeRatios)
    budget: PolicyBudgetGuardrails = Field(default_factory=PolicyBudgetGuardrails)
    thresholds: PolicyThresholds = Field(default_factory=PolicyThresholds)


class PolicyStateUpdate(BaseModel):
    """Partial update payload for policy state."""

    model_config = ConfigDict(extra="forbid")

    mode_ratios: PolicyModeRatios | None = None
    budget: PolicyBudgetGuardrails | None = None
    thresholds: PolicyThresholds | None = None

    @model_validator(mode="after")
    def _require_patch_fields(self) -> PolicyStateUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one policy section must be provided")
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class PolicyStateOut(BaseModel):
    """Serialized policy-state response."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    org_id: uuid.UUID
    scope_type: PolicyScopeType
    scope_id: str | None = None
    state: PolicyStateDocument
    updated_at: datetime


def parse_policy_state(raw_state: dict[str, object] | None) -> PolicyStateDocument:
    """Validate and normalize a stored policy JSON payload."""

    return PolicyStateDocument.model_validate(raw_state or {})


def dump_policy_state(state: PolicyStateDocument) -> dict[str, object]:
    """Convert a validated policy document into JSON-serializable storage."""

    return state.model_dump(mode="json", exclude_none=True)
