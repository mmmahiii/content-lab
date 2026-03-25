"""Reusable persona, constraint, and page-metadata schema models."""

from __future__ import annotations

import re
from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

PersonaExtensionValue: TypeAlias = str | list[str]

_EXTENSION_KEY_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


def _clean_list(
    values: list[str],
    *,
    field_name: str,
    max_items: int = 12,
    item_max_length: int = 160,
) -> list[str]:
    if len(values) > max_items:
        raise ValueError(f"{field_name} can contain at most {max_items} items")

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = _clean_text(raw, field_name=field_name, max_length=item_max_length)
        dedupe_key = item.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(item)
    return normalized


def _clean_extension_key(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("extensions keys must be strings")

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        raise ValueError("extensions keys must not be blank")
    if not _EXTENSION_KEY_RE.fullmatch(normalized):
        raise ValueError("extensions keys must use snake_case and start with a letter")
    return normalized


class PersonaProfile(BaseModel):
    """Phase-1 persona inputs that guide planning and QA."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "label": "Calm educator",
                    "audience": "Busy founders",
                    "brand_tone": ["clear", "grounded"],
                    "content_pillars": ["operations", "positioning"],
                    "differentiators": ["operator-led advice"],
                    "primary_call_to_action": "Book a strategy call",
                    "extensions": {
                        "voice": "plainspoken and specific",
                        "banned_motifs": ["stock trading charts"],
                        "cta_posture": "soft_sell",
                    },
                }
            ]
        },
    )

    label: str = Field(
        min_length=1,
        max_length=120,
        description="Short operator-facing name for the page persona.",
    )
    audience: str = Field(
        min_length=1,
        max_length=240,
        description="Who the page is speaking to in phase-1 planning.",
    )
    brand_tone: list[str] = Field(
        default_factory=list,
        description="Optional tone descriptors used by planning and QA.",
    )
    content_pillars: list[str] = Field(
        default_factory=list,
        description="Required themes the page should consistently create around.",
    )
    differentiators: list[str] = Field(
        default_factory=list,
        description="Optional proof points or strategic edges worth preserving.",
    )
    primary_call_to_action: str | None = Field(
        default=None,
        max_length=160,
        description="Optional default CTA to keep scripts and QA aligned.",
    )
    extensions: dict[str, PersonaExtensionValue] = Field(
        default_factory=dict,
        description=(
            "Reserved structured directives for future persona extensions such as "
            "voice, banned motifs, or CTA posture."
        ),
    )

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

    @field_validator("brand_tone", "content_pillars", "differentiators")
    @classmethod
    def _normalize_string_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return _clean_list(value, field_name=str(info.field_name))

    @field_validator("extensions", mode="before")
    @classmethod
    def _normalize_extensions(cls, value: Any) -> dict[str, PersonaExtensionValue]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(
                "extensions must be an object mapping extension keys to strings or string lists"
            )
        if len(value) > 12:
            raise ValueError("extensions can contain at most 12 items")

        normalized: dict[str, PersonaExtensionValue] = {}
        for raw_key, raw_value in value.items():
            key = _clean_extension_key(raw_key)
            if key in normalized:
                raise ValueError("extensions keys must be unique after normalization")
            if isinstance(raw_value, str):
                normalized[key] = _clean_text(
                    raw_value,
                    field_name=f"extensions.{key}",
                    max_length=160,
                )
                continue
            if isinstance(raw_value, list):
                normalized[key] = _clean_list(
                    raw_value,
                    field_name=f"extensions.{key}",
                    max_items=12,
                )
                continue
            raise ValueError("extensions values must be strings or arrays of strings")
        return normalized

    @model_validator(mode="after")
    def _require_content_pillar(self) -> PersonaProfile:
        if not self.content_pillars:
            raise ValueError("content_pillars must contain at least one item")
        return self


class PageConstraints(BaseModel):
    """High-level content guardrails attached to a page."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "blocked_phrases": ["guaranteed results"],
                    "required_disclosures": ["Results vary"],
                    "allow_direct_cta": True,
                    "max_script_words": 180,
                }
            ]
        },
    )

    banned_topics: list[str] = Field(
        default_factory=list,
        description="Topics planning and QA should avoid entirely.",
    )
    blocked_phrases: list[str] = Field(
        default_factory=list,
        description="Exact phrases or framing to keep out of scripts and captions.",
    )
    required_disclosures: list[str] = Field(
        default_factory=list,
        description="Mandatory disclosure text that must survive planning and QA.",
    )
    prohibited_claims: list[str] = Field(
        default_factory=list,
        description="Claims the page is not allowed to make.",
    )
    preferred_languages: list[str] = Field(
        default_factory=list,
        description="Optional language preferences for content output.",
    )
    allow_direct_cta: bool = Field(
        default=True,
        description="Whether direct calls to action are allowed by default.",
    )
    max_script_words: int | None = Field(
        default=None,
        ge=20,
        le=400,
        description="Optional upper bound for generated script length.",
    )
    max_hashtags: int | None = Field(
        default=None,
        ge=0,
        le=30,
        description="Optional upper bound for caption hashtags.",
    )

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
    def _normalize_constraint_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return _clean_list(value, field_name=str(info.field_name))


class PageMetadata(BaseModel):
    """Validated page metadata shared by page creation, planning, and QA."""

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "examples": [
                {
                    "persona": {
                        "label": "Calm educator",
                        "audience": "Busy founders",
                        "content_pillars": ["operations", "positioning"],
                    },
                    "constraints": {
                        "blocked_phrases": ["guaranteed results"],
                        "allow_direct_cta": True,
                    },
                    "niche": "b2b services",
                }
            ]
        },
    )

    persona: PersonaProfile | None = Field(
        default=None,
        description="Optional page persona used to guide planning and QA.",
    )
    constraints: PageConstraints = Field(
        default_factory=PageConstraints,
        description="Optional page-level creative guardrails and compliance constraints.",
    )


def validate_persona_profile(raw_persona: dict[str, Any]) -> PersonaProfile:
    """Validate and normalize a persona payload for page metadata."""

    return PersonaProfile.model_validate(raw_persona)


def validate_page_metadata(raw_metadata: dict[str, Any] | None) -> PageMetadata:
    """Validate and normalize a page metadata payload."""

    return PageMetadata.model_validate(raw_metadata or {})
