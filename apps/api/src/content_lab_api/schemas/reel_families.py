"""Reel family request/response schemas and serialization helpers."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from content_lab_api.models.reel import Reel, ReelOrigin
from content_lab_api.models.reel_family import ReelFamily


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


class ReelFamilyMode(str, enum.Enum):
    """Locked phase-1 policy modes for concept generation."""

    EXPLOIT = "exploit"
    EXPLORE = "explore"
    MUTATION = "mutation"
    CHAOS = "chaos"


class ReelVariantSummary(BaseModel):
    """Small linked-reel summary embedded in family responses."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    origin: ReelOrigin
    status: str
    variant_label: str | None
    external_reel_id: str | None
    created_at: datetime
    updated_at: datetime


class ReelFamilyCreate(BaseModel):
    """Payload for creating a reel family."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=512)
    mode: ReelFamilyMode = ReelFamilyMode.EXPLORE
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return _clean_text(value, field_name="name", max_length=512)

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if "mode" in value:
            raise ValueError("metadata must not include reserved key 'mode'")
        return value


class ReelFamilyOut(BaseModel):
    """Serialized reel-family response."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    org_id: uuid.UUID
    page_id: uuid.UUID
    name: str
    mode: ReelFamilyMode
    metadata: dict[str, Any]
    variant_count: int
    variants: list[ReelVariantSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


def _split_reel_family_metadata(
    raw_metadata: dict[str, Any] | None,
) -> tuple[ReelFamilyMode, dict[str, Any]]:
    stored = dict(raw_metadata or {})
    raw_mode = stored.pop("mode", ReelFamilyMode.EXPLORE.value)
    return ReelFamilyMode(raw_mode), stored


def dump_reel_family_metadata(mode: ReelFamilyMode, metadata: dict[str, Any]) -> dict[str, Any]:
    """Store the validated top-level mode inside the JSON metadata envelope."""

    payload = dict(metadata)
    payload["mode"] = mode.value
    return payload


def reel_variant_to_summary(reel: Reel) -> ReelVariantSummary:
    """Build a compact variant summary from the ORM row."""

    return ReelVariantSummary(
        id=reel.id,
        origin=ReelOrigin(reel.origin),
        status=reel.status,
        variant_label=reel.variant_label,
        external_reel_id=reel.external_reel_id,
        created_at=reel.created_at,
        updated_at=reel.updated_at,
    )


def reel_family_to_out(family: ReelFamily) -> ReelFamilyOut:
    """Build a response payload from the ORM row."""

    mode, metadata = _split_reel_family_metadata(family.metadata_)
    variants = [
        reel_variant_to_summary(reel)
        for reel in sorted(
            family.reels,
            key=lambda item: (
                item.created_at.isoformat() if item.created_at is not None else "",
                str(item.id),
            ),
        )
    ]
    return ReelFamilyOut(
        id=family.id,
        org_id=family.org_id,
        page_id=family.page_id,
        name=family.name,
        mode=mode,
        metadata=metadata,
        variant_count=len(variants),
        variants=variants,
        created_at=family.created_at,
        updated_at=family.updated_at,
    )
