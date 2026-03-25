"""Page request/response schemas and validation helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from content_lab_api.models.page import Page, PageKind
from content_lab_creative.persona import (
    PageConstraints,
    PageMetadata,
    PersonaProfile,
    validate_page_metadata,
)

__all__ = [
    "PageConstraints",
    "PageCreate",
    "PageMetadata",
    "PageOut",
    "PageUpdate",
    "PersonaProfile",
    "dump_page_metadata",
    "page_to_out",
    "parse_page_metadata",
]


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


class PageCreate(BaseModel):
    """Payload for creating a page."""

    model_config = ConfigDict(extra="forbid")

    platform: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=512)
    external_page_id: str | None = Field(default=None, max_length=256)
    handle: str | None = Field(default=None, max_length=256)
    ownership: PageKind = PageKind.OWNED
    metadata: PageMetadata = Field(
        default_factory=PageMetadata,
        description="Validated page metadata including persona inputs and creative guardrails.",
    )

    @field_validator("platform", mode="before")
    @classmethod
    def _normalize_platform(cls, value: str) -> str:
        return _clean_text(value, field_name="platform", max_length=64).lower()

    @field_validator("display_name", mode="before")
    @classmethod
    def _normalize_display_name(cls, value: str) -> str:
        return _clean_text(value, field_name="display_name", max_length=512)

    @field_validator("external_page_id", "handle", mode="before")
    @classmethod
    def _normalize_optional_identifier(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name=str(info.field_name), max_length=256)


class PageUpdate(BaseModel):
    """Partial update payload for pages."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=512)
    external_page_id: str | None = Field(default=None, max_length=256)
    handle: str | None = Field(default=None, max_length=256)
    ownership: PageKind | None = None
    metadata: PageMetadata | None = Field(
        default=None,
        description="Validated page metadata including persona inputs and creative guardrails.",
    )

    @field_validator("display_name", mode="before")
    @classmethod
    def _normalize_optional_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name="display_name", max_length=512)

    @field_validator("external_page_id", "handle", mode="before")
    @classmethod
    def _normalize_optional_identifier(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name=str(info.field_name), max_length=256)

    @model_validator(mode="after")
    def _require_patch_fields(self) -> PageUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "display_name" in self.model_fields_set and self.display_name is None:
            raise ValueError("display_name cannot be null")
        if "ownership" in self.model_fields_set and self.ownership is None:
            raise ValueError("ownership cannot be null")
        if "metadata" in self.model_fields_set and self.metadata is None:
            raise ValueError("metadata cannot be null")
        return self


class PageOut(BaseModel):
    """Serialized page response."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    org_id: uuid.UUID
    platform: str
    display_name: str
    external_page_id: str | None
    handle: str | None
    ownership: PageKind
    metadata: PageMetadata
    created_at: datetime
    updated_at: datetime


def parse_page_metadata(raw_metadata: dict[str, Any] | None) -> PageMetadata:
    """Validate and normalize the stored metadata envelope."""

    return validate_page_metadata(raw_metadata)


def dump_page_metadata(metadata: PageMetadata) -> dict[str, Any]:
    """Convert validated metadata back into a JSON-serializable dict."""

    return cast(dict[str, Any], metadata.model_dump(mode="json", exclude_none=True))


def page_to_out(page: Page) -> PageOut:
    """Build a response payload from the ORM row."""

    return PageOut(
        id=page.id,
        org_id=page.org_id,
        platform=page.platform,
        display_name=page.display_name,
        external_page_id=page.external_page_id,
        handle=page.handle,
        ownership=PageKind(page.kind),
        metadata=parse_page_metadata(page.metadata_),
        created_at=page.created_at,
        updated_at=page.updated_at,
    )
