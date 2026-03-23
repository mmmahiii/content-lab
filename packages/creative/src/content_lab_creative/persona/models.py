"""Reusable persona and constraint payload models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    """Brand/persona inputs that shape creative generation."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    audience: str = Field(min_length=1, max_length=240)
    brand_tone: list[str] = Field(default_factory=list)
    content_pillars: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    primary_call_to_action: str | None = Field(default=None, max_length=160)

    @field_validator("label", "audience", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        return _clean_text(value, field_name="persona field", max_length=240)

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

    @field_validator("brand_tone", "content_pillars", "differentiators")
    @classmethod
    def _normalize_string_lists(cls, value: list[str], info: Any) -> list[str]:
        return _clean_list(value, field_name=str(info.field_name))

    @model_validator(mode="after")
    def _require_content_pillar(self) -> PersonaProfile:
        if not self.content_pillars:
            raise ValueError("content_pillars must contain at least one item")
        return self


class PageConstraints(BaseModel):
    """High-level content guardrails attached to a page."""

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

    @field_validator(
        "banned_topics",
        "blocked_phrases",
        "required_disclosures",
        "prohibited_claims",
        "preferred_languages",
    )
    @classmethod
    def _normalize_constraint_lists(cls, value: list[str], info: Any) -> list[str]:
        return _clean_list(value, field_name=str(info.field_name))


class PageMetadata(BaseModel):
    """Page metadata envelope with validated persona/constraint sections."""

    model_config = ConfigDict(extra="allow")

    persona: PersonaProfile | None = None
    constraints: PageConstraints = Field(default_factory=PageConstraints)
