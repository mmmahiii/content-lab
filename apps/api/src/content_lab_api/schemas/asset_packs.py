"""Schemas for planned reusable asset packs."""

from __future__ import annotations

import uuid
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
