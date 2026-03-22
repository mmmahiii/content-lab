"""Page request/response schemas and validation helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from content_lab_api.models.page import Page, PageKind


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


def _clean_list(values: list[str], *, field_name: str, max_items: int = 12) -> list[str]:
    if len(values) > max_items:
        raise ValueError(f"{field_name} can contain at most {max_items} items")

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = _clean_text(raw, field_name=field_name, max_length=160)
        dedupe_key = item.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(item)
    return normalized


class PersonaProfile(BaseModel):
    """Validated persona inputs nested inside page metadata."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    audience: str = Field(min_length=1, max_length=240)
    brand_tone: list[str] = Field(default_factory=list)
    content_pillars: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    primary_call_to_action: str | None = Field(default=None, max_length=160)

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, value: str) -> str:
        return _clean_text(value, field_name="label", max_length=120)

    @field_validator("audience", mode="before")
    @classmethod
    def _normalize_audience(cls, value: str) -> str:
        return _clean_text(value, field_name="audience", max_length=240)

    @field_validator("primary_call_to_action", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name="primary_call_to_action", max_length=160)

    @field_validator("brand_tone", "content_pillars", "differentiators", mode="before")
    @classmethod
    def _default_string_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("persona list fields must be arrays of strings")
        return value

    @field_validator("brand_tone")
    @classmethod
    def _normalize_brand_tone(cls, value: list[str]) -> list[str]:
        return _clean_list(value, field_name="brand_tone")

    @field_validator("content_pillars")
    @classmethod
    def _normalize_content_pillars(cls, value: list[str]) -> list[str]:
        return _clean_list(value, field_name="content_pillars")

    @field_validator("differentiators")
    @classmethod
    def _normalize_differentiators(cls, value: list[str]) -> list[str]:
        return _clean_list(value, field_name="differentiators")

    @model_validator(mode="after")
    def _require_content_pillar(self) -> "PersonaProfile":
        if not self.content_pillars:
            raise ValueError("content_pillars must contain at least one item")
        return self


class PageConstraints(BaseModel):
    """Validated content guardrails nested inside page metadata."""

    model_config = ConfigDict(extra="forbid")

    banned_topics: list[str] = Field(default_factory=list)
    blocked_phrases: list[str] = Field(default_factory=list)
    required_disclosures: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    allow_direct_cta: bool = True
    max_script_words: int | None = Field(default=None, ge=20, le=400)
    max_hashtags: int | None = Field(default=None, ge=0, le=30)

    @field_validator(
        "banned_topics",
        "blocked_phrases",
        "required_disclosures",
        "prohibited_claims",
        "preferred_languages",
        mode="before",
    )
    @classmethod
    def _default_constraint_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("constraint list fields must be arrays of strings")
        return value

    @field_validator("banned_topics")
    @classmethod
    def _normalize_banned_topics(cls, value: list[str]) -> list[str]:
        return _clean_list(value, field_name="banned_topics")

    @field_validator("blocked_phrases")
    @classmethod
    def _normalize_blocked_phrases(cls, value: list[str]) -> list[str]:
        return _clean_list(value, field_name="blocked_phrases")

    @field_validator("required_disclosures")
    @classmethod
    def _normalize_required_disclosures(cls, value: list[str]) -> list[str]:
        return _clean_list(value, field_name="required_disclosures")

    @field_validator("prohibited_claims")
    @classmethod
    def _normalize_prohibited_claims(cls, value: list[str]) -> list[str]:
        return _clean_list(value, field_name="prohibited_claims")

    @field_validator("preferred_languages")
    @classmethod
    def _normalize_preferred_languages(cls, value: list[str]) -> list[str]:
        return _clean_list(value, field_name="preferred_languages")


class PageMetadata(BaseModel):
    """Metadata envelope that stores persona and constraint payloads."""

    model_config = ConfigDict(extra="allow")

    persona: PersonaProfile | None = None
    constraints: PageConstraints = Field(default_factory=PageConstraints)


class PageCreate(BaseModel):
    """Payload for creating a page."""

    model_config = ConfigDict(extra="forbid")

    platform: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=512)
    external_page_id: str | None = Field(default=None, max_length=256)
    handle: str | None = Field(default=None, max_length=256)
    ownership: PageKind = PageKind.OWNED
    metadata: PageMetadata = Field(default_factory=PageMetadata)

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
    def _normalize_optional_identifier(cls, value: str | None, info: Any) -> str | None:
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
    metadata: PageMetadata | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def _normalize_optional_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name="display_name", max_length=512)

    @field_validator("external_page_id", "handle", mode="before")
    @classmethod
    def _normalize_optional_identifier(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        return _clean_text(value, field_name=str(info.field_name), max_length=256)

    @model_validator(mode="after")
    def _require_patch_fields(self) -> "PageUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
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

    return PageMetadata.model_validate(raw_metadata or {})


def dump_page_metadata(metadata: PageMetadata) -> dict[str, Any]:
    """Convert validated metadata back into a JSON-serializable dict."""

    return metadata.model_dump(mode="json", exclude_none=True)


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
