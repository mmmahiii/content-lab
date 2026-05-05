"""Schemas for phase-1 asset registry resolution."""

from __future__ import annotations

import uuid
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


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


class AssetResolveRequest(BaseModel):
    """Resolve a generation request through the Asset Registry."""

    model_config = ConfigDict(extra="forbid")

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

    @field_validator("asset_class", mode="before")
    @classmethod
    def _normalize_asset_class(cls, value: str) -> str:
        return _clean_text(value, field_name="asset_class", max_length=64)

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


AssetResolveDecision = Annotated[
    ReuseExactDecision | GenerateDecision | ReuseWithTransformDecision | BlockedDecision,
    Field(discriminator="decision"),
]
