"""Reel request/response schemas and validation helpers."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from content_lab_api.models.reel import (
    GeneratedReelStatus,
    Reel,
    ReelOrigin,
    validate_reel_origin_status,
)
from content_lab_api.schemas.operator_debug import (
    ProcessReelOperatorDebugOut,
    build_process_reel_operator_debug,
)
from content_lab_api.services.process_reel import PROCESS_REEL_METADATA_KEY


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


class ReelReviewInfo(BaseModel):
    """Human review metadata derived from reel metadata."""

    model_config = ConfigDict(extra="forbid")

    approved_at: datetime
    approved_by: str | None = None


class ReelPostingInfo(BaseModel):
    """Human posting metadata derived from reel metadata."""

    model_config = ConfigDict(extra="forbid")

    posted_at: datetime
    posted_by: str | None = None


class ReelCreate(BaseModel):
    """Payload for creating a generated reel variant."""

    model_config = ConfigDict(extra="forbid")

    origin: ReelOrigin = ReelOrigin.GENERATED
    status: GeneratedReelStatus = GeneratedReelStatus.DRAFT
    variant_label: str = Field(min_length=1, max_length=64)
    external_reel_id: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("variant_label", mode="before")
    @classmethod
    def _normalize_variant_label(cls, value: str) -> str:
        return _clean_text(value, field_name="variant_label", max_length=64)

    @field_validator("external_reel_id", mode="before")
    @classmethod
    def _normalize_external_reel_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name="external_reel_id", max_length=256)

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reserved_keys = {"review", "posting"}
        overlaps = sorted(set(value).intersection(reserved_keys))
        if overlaps:
            joined = ", ".join(overlaps)
            raise ValueError(f"metadata must not include reserved key(s): {joined}")
        return value

    @model_validator(mode="after")
    def _validate_generated_only(self) -> ReelCreate:
        if self.origin is not ReelOrigin.GENERATED:
            raise ValueError("origin must be 'generated' for this endpoint")
        if self.external_reel_id is not None:
            raise ValueError("external_reel_id is only allowed for observed reels")
        validate_reel_origin_status(self.origin.value, self.status.value)
        return self


class ReelOut(BaseModel):
    """Serialized reel response."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    org_id: uuid.UUID
    page_id: uuid.UUID
    reel_family_id: uuid.UUID
    origin: ReelOrigin
    status: str
    variant_label: str | None
    external_reel_id: str | None
    metadata: dict[str, Any]
    approved_at: datetime | None = None
    approved_by: str | None = None
    posted_at: datetime | None = None
    posted_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ReelDetailOut(ReelOut):
    """Reel detail with optional process-reel operator debug (same card as run/package)."""

    model_config = ConfigDict(extra="forbid")

    operator_debug: ProcessReelOperatorDebugOut | None = None


def _parse_review_info(raw_metadata: dict[str, Any]) -> ReelReviewInfo | None:
    review = raw_metadata.get("review")
    if not isinstance(review, dict):
        return None
    approved_at = review.get("approved_at")
    if approved_at is None:
        return None
    return ReelReviewInfo.model_validate(review)


def _parse_posting_info(raw_metadata: dict[str, Any]) -> ReelPostingInfo | None:
    posting = raw_metadata.get("posting")
    if not isinstance(posting, dict):
        return None
    posted_at = posting.get("posted_at")
    if posted_at is None:
        return None
    return ReelPostingInfo.model_validate(posting)


def reel_to_out(reel: Reel, *, page_id: uuid.UUID) -> ReelOut:
    """Build a response payload from the ORM row."""

    validate_reel_origin_status(reel.origin, reel.status)
    metadata = dict(reel.metadata_ or {})
    review = _parse_review_info(metadata)
    posting = _parse_posting_info(metadata)
    return ReelOut(
        id=reel.id,
        org_id=reel.org_id,
        page_id=page_id,
        reel_family_id=reel.reel_family_id,
        origin=ReelOrigin(reel.origin),
        status=reel.status,
        variant_label=reel.variant_label,
        external_reel_id=reel.external_reel_id,
        metadata=metadata,
        approved_at=None if review is None else review.approved_at,
        approved_by=None if review is None else review.approved_by,
        posted_at=None if posting is None else posting.posted_at,
        posted_by=None if posting is None else posting.posted_by,
        created_at=reel.created_at,
        updated_at=reel.updated_at,
    )


def reel_to_detail(
    reel: Reel,
    *,
    page_id: uuid.UUID,
    expand_debug: bool = False,
) -> ReelDetailOut:
    """Reel detail including last process-reel summary when present on metadata."""

    base = reel_to_out(reel, page_id=page_id)
    metadata = dict(reel.metadata_ or {})
    process_block = metadata.get(PROCESS_REEL_METADATA_KEY)
    summary = None
    if isinstance(process_block, Mapping):
        raw_summary = process_block.get("last_summary")
        summary = raw_summary if isinstance(raw_summary, Mapping) else None
    operator_debug = build_process_reel_operator_debug(
        workflow_key="process_reel",
        summary=summary,
        tasks=None,
        expand_debug=expand_debug,
    )
    return ReelDetailOut(**base.model_dump(), operator_debug=operator_debug)
