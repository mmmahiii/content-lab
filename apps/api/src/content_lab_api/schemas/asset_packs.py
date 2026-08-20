"""Schemas for planned reusable asset packs."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from content_lab_api.schemas.asset import AssetDetailOut
from content_lab_assets.planner import validate_requested_asset_mix
from content_lab_assets.registry import (
    AssetKind,
    AssetSource,
    MediaType,
    infer_media_type_for_asset_kind,
)
from content_lab_assets.types import AssetSourceMetadata

AssetPackStatusValue = Literal[
    "draft", "planned", "approved", "rejected", "generating", "ready", "failed", "archived"
]
AssetPackItemStatusValue = Literal[
    "planned", "generating", "generated", "uploaded", "imported", "reused", "selected", "failed"
]
PlannedAssetSpecStatusValue = Literal[
    "draft", "planned", "generating", "generated", "registered", "failed", "archived"
]


class AssetPackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=256)
    niche: str = Field(min_length=1, max_length=256)
    purpose: str | None = None
    target_audience: str | None = None
    requested_asset_count: int = Field(default=0, ge=0)
    asset_mix_requested_json: dict[str, Any] | None = None
    strategy_summary: str | None = None


class AssetPackPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=256)
    niche: str = Field(min_length=1, max_length=256)
    requested_asset_count: int = Field(ge=1)
    asset_mix: dict[str, int] | None = None
    target_reel_types: list[str] = Field(default_factory=list)
    style_persona_constraints: dict[str, Any] = Field(default_factory=dict)
    purpose: str | None = None
    target_audience: str | None = None

    @model_validator(mode="after")
    def _validate_asset_mix(self) -> AssetPackPlanRequest:
        self.asset_mix = validate_requested_asset_mix(
            self.asset_mix,
            requested_asset_count=self.requested_asset_count,
        )
        return self


class AssetPackBatchRequest(AssetPackPlanRequest):
    """Plan an asset pack and immediately resolve ready/generation candidates."""

    provider: str = Field(default="runway", min_length=1, max_length=64)
    model: str = Field(default="gen4.5", min_length=1, max_length=64)
    asset_class: str = Field(default="component", min_length=1, max_length=64)
    negative_prompt: str | None = Field(default=None, max_length=4000)
    seed: int | None = Field(default=None, ge=0)
    duration_seconds: float | int | None = Field(default=None, gt=0)
    fps: int | None = Field(default=None, gt=0)
    ratio: str | None = Field(default="9:16", max_length=16)
    motion: dict[str, Any] = Field(default_factory=dict)
    allow_existing_reuse: bool = True
    ready_threshold: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_ready_threshold(self) -> AssetPackBatchRequest:
        if self.ready_threshold is not None and self.ready_threshold > self.requested_asset_count:
            raise ValueError("ready_threshold must be less than or equal to requested_asset_count")
        return self


class ApprovedAssetPackGenerateRequest(BaseModel):
    """Generate an already-reviewed asset pack."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="runway", min_length=1, max_length=64)
    model: str = Field(default="gen4.5", min_length=1, max_length=64)
    asset_class: str = Field(default="component", min_length=1, max_length=64)
    negative_prompt: str | None = Field(default=None, max_length=4000)
    seed: int | None = Field(default=None, ge=0)
    duration_seconds: float | int | None = Field(default=None, gt=0)
    fps: int | None = Field(default=None, gt=0)
    ratio: str | None = Field(default="9:16", max_length=16)
    motion: dict[str, Any] = Field(default_factory=dict)
    allow_existing_reuse: bool = True
    ready_threshold: int | None = Field(default=None, ge=1)


class AssetPackReviewDecisionRequest(BaseModel):
    """Operator review decision metadata for an asset pack plan."""

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetPackRegeneratePlanRequest(AssetPackPlanRequest):
    """Edit requested pack inputs and regenerate the planned specs."""


class AssetPackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    niche: str
    purpose: str | None
    target_audience: str | None
    requested_asset_count: int
    actual_asset_count: int = 0
    asset_mix_requested_json: dict[str, Any] | None
    asset_mix_final_json: dict[str, Any] | None
    status: AssetPackStatusValue
    strategy_summary: str | None
    created_at: datetime
    updated_at: datetime


class AssetPackItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID | None = None
    planned_asset_spec_id: uuid.UUID | None = None
    asset_kind: str = Field(min_length=1, max_length=64)
    pack_role: str = Field(min_length=1, max_length=128)
    reuse_purpose: str | None = None
    priority: int = 0
    status: AssetPackItemStatusValue = "planned"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    compatibility_metadata: dict[str, Any] = Field(default_factory=dict)


class AssetPackItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_pack_id: uuid.UUID
    asset_id: uuid.UUID | None
    planned_asset_spec_id: uuid.UUID | None
    asset_kind: str
    pack_role: str
    reuse_purpose: str | None
    priority: int
    status: AssetPackItemStatusValue
    metadata_json: dict[str, Any]
    compatibility_metadata: dict[str, Any]
    created_at: datetime


class PlannedAssetSpecCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_kind: str = Field(min_length=1, max_length=64)
    media_type: str = Field(min_length=1, max_length=64)
    working_title: str = Field(min_length=1, max_length=256)
    purpose: str = Field(min_length=1)
    prompt_or_description: str = Field(min_length=1)
    required_traits: dict[str, Any] = Field(default_factory=dict)
    compatible_with: dict[str, Any] = Field(default_factory=dict)
    compatibility_metadata: dict[str, Any] = Field(default_factory=dict)
    intended_reel_formats: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=0)
    estimated_reuse_count: int = Field(default=0, ge=0)
    status: PlannedAssetSpecStatusValue = "draft"


class PlannedAssetSpecOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_pack_id: uuid.UUID
    asset_kind: str
    media_type: str
    working_title: str
    purpose: str
    prompt_or_description: str
    required_traits: dict[str, Any]
    compatible_with: dict[str, Any]
    compatibility_metadata: dict[str, Any]
    intended_reel_formats: list[str]
    priority: int
    estimated_reuse_count: int
    status: PlannedAssetSpecStatusValue
    created_at: datetime
    updated_at: datetime


class PlannedAssetSpecPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_pack_id: uuid.UUID
    asset_kind: str
    media_type: str
    category: str
    working_title: str
    purpose: str
    prompt_or_description: str
    rationale: str
    required_traits: dict[str, Any]
    compatible_with: dict[str, Any]
    compatibility_metadata: dict[str, Any]
    intended_reel_formats: list[str]
    priority: int
    estimated_reuse_count: int
    output_potential_score: float
    output_potential_scores: dict[str, float]
    output_potential_rationale: list[str]
    status: PlannedAssetSpecStatusValue
    created_at: datetime
    updated_at: datetime


class AssetPackPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_pack: AssetPackOut
    asset_pack_plan: dict[str, Any]
    asset_mix: dict[str, int]
    planned_asset_specs: list[PlannedAssetSpecPlanOut]
    strategy_summary: str
    reuse_rationale: str
    expected_reel_formats: list[str]
    planning_resolution_summary: dict[str, int] = Field(default_factory=dict)


class AssetPackBatchOut(AssetPackPlanOut):
    """Result of batch asset-pack planning and resolution."""

    items: list[AssetPackItemOut]
    resolution_summary: dict[str, int]
    generation_decisions: list[dict[str, Any]]


class AssetLedIdeasRequest(BaseModel):
    """Generate reel ideas from ready assets already attached to an asset pack."""

    model_config = ConfigDict(extra="forbid")

    selected_asset_ids: list[uuid.UUID] | None = None
    target_concept_count: int = Field(default=5, ge=1, le=25)
    format_filters: list[str] | None = None
    style_filters: list[str] | None = None
    selection_mode: Literal["balanced", "exploit", "explore", "mutation", "chaos"] = "balanced"


class AssetLedReelBriefOut(BaseModel):
    """Structured reel brief derived from one compatible asset combination."""

    model_config = ConfigDict(extra="forbid")

    concept_title: str
    hook: str
    visual_sequence: list[str]
    selected_asset_ids: list[uuid.UUID]
    composition_intent: str
    overlay_plan: str
    audio_direction: str
    caption_angle: str
    posting_plan_seed: dict[str, Any]


class AssetLedConceptOut(BaseModel):
    """Ranked candidate concept with source asset lineage."""

    model_config = ConfigDict(extra="forbid")

    idea: str
    source_composition_id: str
    source_asset_ids: list[uuid.UUID]
    compatible_formats: list[str]
    emotional_angles: list[str]
    selection_score: float
    reasons: list[str]
    brief: AssetLedReelBriefOut


class AssetLedIdeasOut(BaseModel):
    """Asset-led concept generation result for one pack."""

    model_config = ConfigDict(extra="forbid")

    asset_pack: AssetPackOut
    concepts: list[AssetLedConceptOut]


class AssetPackCombinationsRequest(BaseModel):
    """Generate reel composition candidates from ready pack assets."""

    model_config = ConfigDict(extra="forbid")

    target_reel_count: int = Field(default=5, ge=1, le=100)
    filters: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["balanced", "exploit", "explore", "mutation", "chaos"] = "balanced"

    def format_filters(self) -> list[str] | None:
        return _optional_filter_values(self.filters, "format", "formats", "format_filters")

    def style_filters(self) -> list[str] | None:
        return _optional_filter_values(self.filters, "style", "styles", "style_filters")


class CandidateCompositionAssetOut(BaseModel):
    """One asset assigned to a role in a composition candidate."""

    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    asset_kind: str
    pack_role: str | None = None
    title: str | None = None
    compatibility: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    performance_score: float | None = None
    usage_count: int = 0


class CandidateCompositionOut(BaseModel):
    """API-friendly composition candidate that can feed render workflows."""

    model_config = ConfigDict(extra="forbid")

    composition_id: str
    roles: dict[str, CandidateCompositionAssetOut]
    compatibility_score: float
    diversity_score: float
    performance_score: float
    selection_score: float
    reasons: list[str] = Field(default_factory=list)
    composition_manifest: dict[str, Any]


class AssetPackCombinationsOut(BaseModel):
    """Candidate composition response for one asset pack."""

    model_config = ConfigDict(extra="forbid")

    asset_pack: AssetPackOut
    candidate_compositions: list[CandidateCompositionOut]


class AssetPackCompositionSubmitRequest(BaseModel):
    """Submit a selected composition manifest for asynchronous process_reel work."""

    model_config = ConfigDict(extra="forbid")

    page_id: uuid.UUID
    composition_manifest: dict[str, Any] = Field(default_factory=dict)
    render_mode: Literal["preview", "final"] = "preview"
    dry_run: bool = True
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetPackCompositionSubmitOut(BaseModel):
    """Queued render submission for a selected asset composition."""

    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    task_id: uuid.UUID
    reel_id: uuid.UUID
    reel_family_id: uuid.UUID
    status: str
    external_ref: str | None
    accepted_for_rendering: bool = True


class CinematicPlanPromptRequest(BaseModel):
    """Build a manual ChatGPT prompt from selected registry assets."""

    model_config = ConfigDict(extra="forbid")

    page_id: uuid.UUID
    selected_asset_ids: list[uuid.UUID] = Field(min_length=1)
    content_goal: str | None = Field(default=None, max_length=1000)
    brand_persona_constraints: dict[str, Any] = Field(default_factory=dict)
    platform_constraints: dict[str, Any] = Field(default_factory=dict)
    duration_target_seconds: float | None = Field(default=None, gt=0, le=180)
    pinned_prompt_paths: list[str] = Field(default_factory=list)
    banned_prompt_paths: list[str] = Field(default_factory=list)

    @field_validator("selected_asset_ids")
    @classmethod
    def _dedupe_selected_assets(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        result: list[uuid.UUID] = []
        for asset_id in value:
            if asset_id not in result:
                result.append(asset_id)
        return result


class CinematicPlanPromptOut(BaseModel):
    """Exact prompt package to paste into ChatGPT."""

    model_config = ConfigDict(extra="forbid")

    recommended_model: str
    planning_prompt_version: str
    input_page_context_hash: str
    selected_asset_ids: list[uuid.UUID]
    suggested_prompt_paths: list[str]
    prompt_path_eligibility: dict[str, Any]
    master_prompt: str
    planner_input: dict[str, Any]


class CinematicPlanValidateRequest(CinematicPlanPromptRequest):
    """Validate a pasted ChatGPT cinematic plan."""

    raw_plan_json: str | None = None
    plan: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _require_plan_payload(self) -> CinematicPlanValidateRequest:
        if not self.raw_plan_json and self.plan is None:
            raise ValueError("raw_plan_json or plan is required")
        return self


class CinematicPlanValidateOut(BaseModel):
    """Validated canonical plan and derived JSON artifact files."""

    model_config = ConfigDict(extra="forbid")

    plan: dict[str, Any]
    validation_report: dict[str, Any]
    plan_hash: str
    artifacts: dict[str, Any]


def _optional_filter_values(
    filters: Mapping[str, Any],
    *keys: str,
) -> list[str] | None:
    for key in keys:
        value = filters.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
    return None


class SourceAssetRegisterRequest(BaseModel):
    """Register user-provided bytes as a reusable asset pack member."""

    model_config = ConfigDict(extra="forbid")

    asset_class: str = Field(default="component", min_length=1, max_length=64)
    asset_kind: AssetKind
    media_type: MediaType | None = None
    asset_source: AssetSource = AssetSource.UPLOADED
    pack_role: str = Field(min_length=1, max_length=128)
    reuse_purpose: str | None = None
    priority: int = Field(default=0, ge=0)
    planned_asset_spec_id: uuid.UUID | None = None
    filename: str | None = Field(default=None, min_length=1, max_length=256)
    content_type: str | None = Field(default=None, min_length=1, max_length=128)
    data_base64: str = Field(min_length=1)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: float | None = Field(default=None, gt=0)
    duration_seconds: float | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_metadata: AssetSourceMetadata | None = None

    @model_validator(mode="after")
    def _validate_source_registration(self) -> SourceAssetRegisterRequest:
        if self.media_type is None:
            self.media_type = infer_media_type_for_asset_kind(self.asset_kind)
        if self.asset_source is AssetSource.GENERATED:
            raise ValueError("source asset registration cannot use asset_source='generated'")
        return self

    @field_validator("data_base64", mode="before")
    @classmethod
    def _normalize_data_base64(cls, value: str) -> str:
        normalized = "".join(str(value).strip().split())
        if not normalized:
            raise ValueError("data_base64 must not be blank")
        return normalized


class SourceAssetRegisterOut(BaseModel):
    """Registered source asset plus the pack item it is attached to."""

    model_config = ConfigDict(extra="forbid")

    asset: AssetDetailOut
    item: AssetPackItemOut
    reused_existing_asset: bool = False
