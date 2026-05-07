"""Schemas for phase-1 asset registry resolution."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from content_lab_assets.registry import (
    AssetKind,
    AssetSource,
    BlockedDecision,
    GenerateDecision,
    MediaType,
    ReuseExactDecision,
    ReuseWithTransformDecision,
    infer_media_type_for_asset_kind,
    validate_asset_kind_media_type,
)
from content_lab_assets.types import AssetSourceMetadata

_COMPONENT_ROLE_ASSET_KIND_ALIASES: dict[str, AssetKind] = {
    "background": AssetKind.BACKGROUND_VIDEO,
    "background_video": AssetKind.BACKGROUND_VIDEO,
    "background_image": AssetKind.BACKGROUND_IMAGE,
    "object": AssetKind.OBJECT_IMAGE,
    "object_image": AssetKind.OBJECT_IMAGE,
    "object_png": AssetKind.TRANSPARENT_CUTOUT_PNG,
    "subject": AssetKind.SUBJECT_VIDEO,
    "subject_video": AssetKind.SUBJECT_VIDEO,
    "subject_image": AssetKind.SUBJECT_IMAGE,
    "hook": AssetKind.HOOK_TEXT,
    "hook_text": AssetKind.HOOK_TEXT,
    "audio": AssetKind.AUDIO_TRACK,
    "audio_track": AssetKind.AUDIO_TRACK,
    "effect": AssetKind.EFFECT_VIDEO,
    "effect_layer": AssetKind.EFFECT_VIDEO,
    "transition": AssetKind.TRANSITION_LAYER,
    "transition_layer": AssetKind.TRANSITION_LAYER,
}


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


class AssetResolveRequest(BaseModel):
    """Resolve an asset or individual component requirement through the Asset Registry."""

    model_config = ConfigDict(extra="forbid")

    component_role: str | None = Field(default=None, min_length=1, max_length=64)
    layer_role: str | None = Field(default=None, min_length=1, max_length=64)
    sequence_index: int | None = Field(default=None, ge=0)
    z_index: int | None = None
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, ge=0)
    transform_recipe: dict[str, Any] | None = None
    transform_version: str | None = Field(default=None, max_length=64)
    asset_class: str = Field(min_length=1, max_length=64)
    asset_kind: AssetKind = AssetKind.GENERATED_CLIP
    media_type: MediaType | None = None
    asset_source: AssetSource = AssetSource.GENERATED
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=4000)
    negative_prompt: str | None = Field(default=None, max_length=4000)
    seed: int | None = Field(default=None, ge=0)
    duration_seconds: float | int | None = Field(default=None, gt=0)
    fps: int | None = Field(default=None, gt=0)
    ratio: str | None = Field(default=None, max_length=16)
    motion: dict[str, Any] = Field(default_factory=dict)
    init_image_hash: str | None = Field(default=None, max_length=128)
    reference_asset_ids: list[uuid.UUID] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_metadata: AssetSourceMetadata | None = None

    @model_validator(mode="before")
    @classmethod
    def _unwrap_component_requirement(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        component_requirement = data.pop("component_requirement", None)
        if isinstance(component_requirement, Mapping):
            merged = dict(component_requirement)
            merged.update(data)
            data = merged

        role = data.get("component_role") or data.get("role")
        if role is not None and "component_role" not in data:
            data["component_role"] = role
        if role is not None and "asset_kind" not in data:
            alias_key = _normalize_component_role_alias(str(role))
            if alias_key in _COMPONENT_ROLE_ASSET_KIND_ALIASES:
                data["asset_kind"] = _COMPONENT_ROLE_ASSET_KIND_ALIASES[alias_key].value
        if "asset_class" not in data and role is not None:
            data["asset_class"] = "component"
        return data

    @model_validator(mode="after")
    def _validate_media_type(self) -> AssetResolveRequest:
        if self.media_type is None:
            self.media_type = infer_media_type_for_asset_kind(self.asset_kind)
            return self
        self.media_type = validate_asset_kind_media_type(
            asset_kind=self.asset_kind,
            media_type=self.media_type,
        )
        return self

    @model_validator(mode="after")
    def _validate_component_timing(self) -> AssetResolveRequest:
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be greater than start_time")
        return self

    @field_validator("asset_class", "component_role", "layer_role", mode="before")
    @classmethod
    def _normalize_short_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name=str(info.field_name), max_length=64)

    @field_validator("provider", "model", mode="before")
    @classmethod
    def _normalize_provider_fields(cls, value: str, info: ValidationInfo) -> str:
        return _clean_text(value, field_name=str(info.field_name), max_length=64)

    @field_validator("ratio", mode="before")
    @classmethod
    def _normalize_ratio(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name="ratio", max_length=16)

    @field_validator("init_image_hash", mode="before")
    @classmethod
    def _normalize_init_image_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name="init_image_hash", max_length=128)

    @field_validator("prompt", mode="before")
    @classmethod
    def _normalize_prompt(cls, value: str) -> str:
        return _clean_text(value, field_name="prompt", max_length=4000)

    @field_validator("negative_prompt", mode="before")
    @classmethod
    def _normalize_negative_prompt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name="negative_prompt", max_length=4000)

    def component_metadata(self) -> dict[str, Any]:
        """Return normalized component lineage metadata for decision provenance."""

        return {
            key: value
            for key, value in {
                "component_role": self.component_role,
                "layer_role": self.layer_role,
                "sequence_index": self.sequence_index,
                "z_index": self.z_index,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "transform_recipe": self.transform_recipe,
                "transform_version": self.transform_version,
            }.items()
            if value is not None
        }


def _normalize_component_role_alias(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", "_").split())


AssetResolveDecision = Annotated[
    ReuseExactDecision | GenerateDecision | ReuseWithTransformDecision | BlockedDecision,
    Field(discriminator="decision"),
]


class ApprovedExternalImportRequest(BaseModel):
    """Operator-approved fetch of an external URL into org object storage (no blind scraping)."""

    model_config = ConfigDict(extra="forbid")

    asset_class: str = Field(default="component", min_length=1, max_length=64)
    asset_kind: AssetKind
    media_type: MediaType | None = None
    external_source_url: str = Field(min_length=8, max_length=2048)
    usage_rights_confirmed: bool = False
    source_metadata: AssetSourceMetadata
    planned_asset_pack_id: uuid.UUID | None = None
    planned_asset_spec_id: uuid.UUID | None = None
    pack_role: str = Field(default="approved_external_import", min_length=1, max_length=128)
    filename: str | None = Field(default=None, min_length=1, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_media(self) -> ApprovedExternalImportRequest:
        if self.media_type is None:
            self.media_type = infer_media_type_for_asset_kind(self.asset_kind)
            return self
        self.media_type = validate_asset_kind_media_type(
            asset_kind=self.asset_kind,
            media_type=self.media_type,
        )
        return self

    @model_validator(mode="after")
    def _require_usage_confirmation(self) -> ApprovedExternalImportRequest:
        if not self.usage_rights_confirmed:
            raise ValueError("usage_rights_confirmed must be true before importing external bytes")
        return self

    @model_validator(mode="after")
    def _require_source_provider(self) -> ApprovedExternalImportRequest:
        if not (self.source_metadata.source_provider or "").strip():
            raise ValueError("source_metadata.source_provider is required for approved imports")
        return self


class ApprovedExternalImportOut(BaseModel):
    """Result of an approved external import."""

    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    reused_existing_asset: bool = False
    import_warnings: list[str] = Field(default_factory=list)
    licence_metadata_complete: bool = True
    asset_pack_item_id: uuid.UUID | None = None


class AssetLibraryItemOut(BaseModel):
    """Operator-facing asset library row with component-aware metadata."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    org_id: uuid.UUID
    asset_class: str
    asset_kind: str | None = None
    media_type: str | None = None
    niche: str | None = None
    tags: list[str] = Field(default_factory=list)
    asset_pack_ids: list[uuid.UUID] = Field(default_factory=list)
    has_transparency: bool | None = None
    ready_status: str
    performance_score: float | None = None
    reuse_count: int = 0
    source: str
    storage_uri: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
