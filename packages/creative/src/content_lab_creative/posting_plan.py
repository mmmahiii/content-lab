"""Deterministic posting-plan artifact generation for ready-to-post packages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from content_lab_core.types import Platform
from content_lab_creative.persona import PageMetadata
from content_lab_creative.types import ApplicablePolicyState, CreativeMode, PolicyStateDocument

_POSTING_WINDOWS: tuple[tuple[str, str], ...] = (
    ("monday", "09:00"),
    ("tuesday", "12:30"),
    ("wednesday", "15:00"),
    ("thursday", "18:30"),
    ("friday", "11:00"),
    ("saturday", "10:30"),
    ("sunday", "17:00"),
)
_PRIORITY_BY_MODE: dict[CreativeMode, Literal["high", "normal", "low"]] = {
    CreativeMode.EXPLOIT: "high",
    CreativeMode.EXPLORE: "normal",
    CreativeMode.MUTATION: "normal",
    CreativeMode.CHAOS: "low",
}
_CAPTION_VARIANT_BY_MODE: dict[CreativeMode, str] = {
    CreativeMode.EXPLOIT: "standard",
    CreativeMode.EXPLORE: "engagement",
    CreativeMode.MUTATION: "short",
    CreativeMode.CHAOS: "short",
}


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = " ".join(str(value).strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


def _clean_optional_text(
    value: str | None,
    *,
    field_name: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    return _clean_text(value, field_name=field_name, max_length=max_length)


def _stable_json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _stable_json_value(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _stable_json_value(raw_value)
            for key, raw_value in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_stable_json_value(item) for item in value]
    return value


class PostingPlanPageContext(BaseModel):
    """Page context carried into deterministic posting-plan generation."""

    model_config = ConfigDict(extra="forbid")

    page_id: str | None = None
    page_name: str = Field(min_length=1, max_length=160)
    page_metadata: PageMetadata = Field(default_factory=PageMetadata)
    target_platforms: list[Platform] = Field(default_factory=lambda: [Platform.INSTAGRAM])
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    locale: str = Field(default="en", min_length=2, max_length=32)

    @field_validator("page_id", mode="before")
    @classmethod
    def _normalize_page_id(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, field_name="page_id", max_length=128)

    @field_validator("page_name", mode="before")
    @classmethod
    def _normalize_page_name(cls, value: str) -> str:
        return _clean_text(value, field_name="page_name", max_length=160)

    @field_validator("timezone", mode="before")
    @classmethod
    def _normalize_timezone(cls, value: str) -> str:
        return _clean_text(value, field_name="timezone", max_length=64)

    @field_validator("locale", mode="before")
    @classmethod
    def _normalize_locale(cls, value: str) -> str:
        return _clean_text(value, field_name="locale", max_length=32)

    @field_validator("target_platforms", mode="before")
    @classmethod
    def _default_platforms(cls, value: list[Platform] | None) -> list[Platform]:
        if value is None or len(value) == 0:
            return [Platform.INSTAGRAM]
        return value

    @field_validator("target_platforms")
    @classmethod
    def _normalize_platforms(cls, value: list[Platform]) -> list[Platform]:
        unique = {platform.value: platform for platform in value}
        return [unique[key] for key in sorted(unique)]


class PostingPlanFamilyContext(BaseModel):
    """Family-level context for posting-plan selection and display."""

    model_config = ConfigDict(extra="forbid")

    family_id: str | None = None
    family_name: str = Field(min_length=1, max_length=200)
    content_pillar: str = Field(min_length=1, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("family_id", mode="before")
    @classmethod
    def _normalize_family_id(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, field_name="family_id", max_length=128)

    @field_validator("family_name", mode="before")
    @classmethod
    def _normalize_family_name(cls, value: str) -> str:
        return _clean_text(value, field_name="family_name", max_length=200)

    @field_validator("content_pillar", mode="before")
    @classmethod
    def _normalize_content_pillar(cls, value: str) -> str:
        return _clean_text(value, field_name="content_pillar", max_length=160)


class PostingPlanVariantContext(BaseModel):
    """Variant-specific context for package handoff and publishing review."""

    model_config = ConfigDict(extra="forbid")

    variant_id: str | None = None
    variant_label: str = Field(min_length=1, max_length=80)
    variant_index: int = Field(default=0, ge=0)
    duration_seconds: int | None = Field(default=None, ge=1, le=180)

    @field_validator("variant_id", mode="before")
    @classmethod
    def _normalize_variant_id(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, field_name="variant_id", max_length=128)

    @field_validator("variant_label", mode="before")
    @classmethod
    def _normalize_variant_label(cls, value: str) -> str:
        return _clean_text(value, field_name="variant_label", max_length=80)


class PostingWindow(BaseModel):
    """Recommended human posting window derived from the plan fingerprint."""

    model_config = ConfigDict(extra="forbid")

    day_offset: int = Field(ge=0, le=len(_POSTING_WINDOWS) - 1)
    weekday: str = Field(min_length=1, max_length=16)
    local_time: str = Field(min_length=1, max_length=16)
    timezone: str = Field(min_length=1, max_length=64)


class PostingPlanPublication(BaseModel):
    """Human-facing posting instructions for a reel package."""

    model_config = ConfigDict(extra="forbid")

    posting_method: Literal["manual"] = "manual"
    approval_required: bool = True
    priority: Literal["high", "normal", "low"]
    target_platforms: list[Platform] = Field(default_factory=list)
    recommended_caption_variant: str = Field(min_length=1, max_length=32)
    publish_window: PostingWindow
    review_focus: list[str] = Field(default_factory=list)


class PostingPlanCompliance(BaseModel):
    """Pulled-forward policy and page guardrails relevant to manual posting."""

    model_config = ConfigDict(extra="forbid")

    allow_direct_cta: bool
    required_disclosures: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    blocked_phrases: list[str] = Field(default_factory=list)
    max_hashtags: int | None = Field(default=None, ge=0, le=30)


class PostingPlanTrace(BaseModel):
    """Deterministic trace explaining how the posting plan was selected."""

    model_config = ConfigDict(extra="forbid")

    algorithm_version: Literal["phase_1"] = "phase_1"
    seed_material: str
    seed_hash: str
    seed_bucket: float = Field(ge=0.0, le=1.0)
    posting_window_index: int = Field(ge=0, le=len(_POSTING_WINDOWS) - 1)


class PostingPlanArtifact(BaseModel):
    """Stable JSON-ready posting plan for package QA and web display."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["phase_1"] = "phase_1"
    artifact_type: Literal["posting_plan"] = "posting_plan"
    plan_fingerprint: str
    mode: CreativeMode
    page: PostingPlanPageContext
    family: PostingPlanFamilyContext
    variant: PostingPlanVariantContext
    policy_snapshot: PolicyStateDocument
    publication: PostingPlanPublication
    compliance: PostingPlanCompliance
    trace: PostingPlanTrace


def build_posting_plan(
    *,
    policy: ApplicablePolicyState | PolicyStateDocument | Mapping[str, Any],
    page: PostingPlanPageContext | Mapping[str, Any],
    family: PostingPlanFamilyContext | Mapping[str, Any],
    mode: CreativeMode | str,
    variant: PostingPlanVariantContext | Mapping[str, Any],
) -> PostingPlanArtifact:
    """Build a deterministic posting-plan artifact from policy and variant context."""

    policy_snapshot = _coerce_policy_document(policy)
    page_context = PostingPlanPageContext.model_validate(page)
    family_context = PostingPlanFamilyContext.model_validate(family)
    variant_context = PostingPlanVariantContext.model_validate(variant)
    selected_mode = CreativeMode(mode)

    seed_material = json.dumps(
        _stable_json_value(
            {
                "policy": policy_snapshot,
                "page": page_context,
                "family": family_context,
                "mode": selected_mode,
                "variant": variant_context,
            }
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    seed_hash = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
    seed_bucket = int(seed_hash[:16], 16) / 2**64
    posting_window_index = int(seed_hash[16:24], 16) % len(_POSTING_WINDOWS)
    weekday, local_time = _POSTING_WINDOWS[posting_window_index]

    return PostingPlanArtifact(
        plan_fingerprint=f"sha256:{seed_hash}",
        mode=selected_mode,
        page=page_context,
        family=family_context,
        variant=variant_context,
        policy_snapshot=policy_snapshot,
        publication=PostingPlanPublication(
            priority=_PRIORITY_BY_MODE[selected_mode],
            target_platforms=list(page_context.target_platforms),
            recommended_caption_variant=_CAPTION_VARIANT_BY_MODE[selected_mode],
            publish_window=PostingWindow(
                day_offset=posting_window_index,
                weekday=weekday,
                local_time=local_time,
                timezone=page_context.timezone,
            ),
            review_focus=_review_focus(page_context=page_context),
        ),
        compliance=PostingPlanCompliance(
            allow_direct_cta=page_context.page_metadata.constraints.allow_direct_cta,
            required_disclosures=list(page_context.page_metadata.constraints.required_disclosures),
            prohibited_claims=list(page_context.page_metadata.constraints.prohibited_claims),
            blocked_phrases=list(page_context.page_metadata.constraints.blocked_phrases),
            max_hashtags=page_context.page_metadata.constraints.max_hashtags,
        ),
        trace=PostingPlanTrace(
            seed_material=seed_material,
            seed_hash=seed_hash,
            seed_bucket=seed_bucket,
            posting_window_index=posting_window_index,
        ),
    )


def serialize_posting_plan_json(plan: PostingPlanArtifact | Mapping[str, Any]) -> str:
    """Serialize a posting-plan artifact into a stable JSON payload."""

    return json.dumps(
        _stable_json_value(plan),
        sort_keys=True,
        separators=(",", ":"),
    )


def _coerce_policy_document(
    policy: ApplicablePolicyState | PolicyStateDocument | Mapping[str, Any],
) -> PolicyStateDocument:
    if isinstance(policy, ApplicablePolicyState):
        return policy.effective_policy
    if isinstance(policy, PolicyStateDocument):
        return policy
    return PolicyStateDocument.model_validate(policy)


def _review_focus(*, page_context: PostingPlanPageContext) -> list[str]:
    constraints = page_context.page_metadata.constraints
    focus = [
        "Human review is required before any posting action.",
        "Confirm the selected caption and final assets still match the page persona.",
    ]
    if constraints.required_disclosures:
        focus.append("Carry required disclosures into the final caption or on-screen overlays.")
    if constraints.prohibited_claims or constraints.blocked_phrases:
        focus.append("Check claims and blocked phrases against page-level guardrails.")
    if constraints.max_hashtags is not None:
        focus.append(f"Keep hashtag count at or below {constraints.max_hashtags}.")
    if not constraints.allow_direct_cta:
        focus.append("Avoid direct calls to action in the final posting copy.")
    return focus


__all__ = [
    "PostingPlanArtifact",
    "PostingPlanCompliance",
    "PostingPlanFamilyContext",
    "PostingPlanPageContext",
    "PostingPlanPublication",
    "PostingPlanTrace",
    "PostingPlanVariantContext",
    "PostingWindow",
    "build_posting_plan",
    "serialize_posting_plan_json",
]
