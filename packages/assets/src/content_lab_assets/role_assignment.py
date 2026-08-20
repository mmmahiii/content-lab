"""Cinematic role assignment helpers for selected Asset Registry items."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from content_lab_assets.metadata import derive_asset_compatibility_metadata
from content_lab_assets.types import AssetKind, infer_media_type_for_asset_kind

CINEMATIC_ROLES: tuple[str, ...] = (
    "hero_subject",
    "supporting_subject",
    "environment_base",
    "background_reveal",
    "foreground_texture",
    "atmospheric_layer",
    "motion_layer",
    "audio_layer",
    "caption_support",
    "transition_element",
    "brand_marker",
    "narrative_payoff",
)

# Whole-token match on alphanumeric tokens scanned from identifiers (eggplant ≠ plant).
_FRESHNESS_BACKGROUND_REVEAL_TOKENS = frozenset(
    {"plant", "plants", "herb", "herbs", "foliage", "greenery", "basil", "rosemary", "mint", "cilantro"}
)


class CinematicAssetDescriptor(BaseModel):
    """Prompt-safe descriptor for one selected registry asset."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    asset_label: str = Field(min_length=1)
    asset_kind: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    pack_role: str | None = None
    transparent: bool = False
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    tags: list[str] = Field(default_factory=list)
    possible_cinematic_roles: list[str] = Field(default_factory=list, min_length=1)
    compatibility: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("possible_cinematic_roles")
    @classmethod
    def _validate_roles(cls, value: list[str]) -> list[str]:
        unknown = [role for role in value if role not in CINEMATIC_ROLES]
        if unknown:
            raise ValueError(f"unknown cinematic roles: {', '.join(unknown)}")
        return _dedupe(value)


def normalize_asset_for_cinematic_planning(item: Mapping[str, Any]) -> CinematicAssetDescriptor:
    """Return a compact, deterministic asset descriptor for prompt planning."""

    metadata = _mapping(item.get("metadata") or item.get("metadata_json"))
    compatibility = _mapping(
        item.get("compatibility")
        or item.get("compatibility_metadata")
        or metadata.get("compatibility")
    )
    asset_kind = _required_text(
        item.get("asset_kind") or metadata.get("asset_kind"),
        field_name="asset_kind",
    )
    try:
        media_type = str(item.get("media_type") or metadata.get("media_type") or infer_media_type_for_asset_kind(asset_kind).value)
    except ValueError:
        media_type = str(item.get("media_type") or metadata.get("media_type") or "unknown")
    pack_role = _optional_text(item.get("pack_role") or item.get("role") or metadata.get("pack_role"))
    label = _first_text(
        item.get("asset_label"),
        item.get("title"),
        item.get("reuse_purpose"),
        metadata.get("title"),
        metadata.get("working_title"),
        metadata.get("description"),
        pack_role,
        asset_kind,
    )
    possible_roles = list(
        cinematic_roles_for_asset(
            asset_kind=asset_kind,
            media_type=media_type,
            pack_role=pack_role,
            metadata=metadata,
        )
    )
    width = _positive_int(metadata.get("width") or _mapping(metadata.get("visual")).get("width"))
    height = _positive_int(metadata.get("height") or _mapping(metadata.get("visual")).get("height"))
    transparency = _mapping(metadata.get("transparency"))
    if not transparency and _has_transparency(metadata):
        transparency = {"has_transparency": True}
    planner_compatibility = derive_asset_compatibility_metadata(
        asset_kind=asset_kind,
        transparency=transparency,
        width=width,
        height=height,
        possible_cinematic_roles=possible_roles,
        overrides=compatibility,
    ).model_dump(mode="json")
    return CinematicAssetDescriptor(
        asset_id=_required_text(item.get("asset_id") or item.get("id"), field_name="asset_id"),
        asset_label=label,
        asset_kind=asset_kind,
        media_type=media_type,
        pack_role=pack_role,
        transparent=_has_transparency(metadata),
        width=width,
        height=height,
        tags=_string_list(metadata.get("tags"))[:8],
        possible_cinematic_roles=possible_roles,
        compatibility=planner_compatibility,
        metadata=_prompt_safe_metadata(metadata),
    )


def cinematic_roles_for_asset(
    *,
    asset_kind: str | AssetKind,
    media_type: str | None = None,
    pack_role: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Infer possible cinematic roles from registry kind, pack role, and metadata."""

    kind = _normalize(str(asset_kind))
    role_text = _normalize(pack_role or "")
    media = _normalize(media_type or "")
    metadata_text = _normalize(" ".join(_metadata_hints(metadata or {})))
    haystack = " ".join([kind, role_text, media, metadata_text])
    roles: list[str] = []

    hint_tokens = set(re.findall(r"[a-z0-9]+", haystack.lower()))
    if hint_tokens.intersection(_FRESHNESS_BACKGROUND_REVEAL_TOKENS):
        roles.append("background_reveal")

    if any(token in haystack for token in ("audio", "sound", "voiceover", "music")):
        roles.append("audio_layer")
        if media == "audio":
            return tuple(role for role in _dedupe(roles) if role in CINEMATIC_ROLES)
    if "background" in haystack or "environment" in haystack or "scene_setter" in haystack:
        roles.extend(["environment_base", "background_reveal"])
    if any(token in haystack for token in ("subject", "hero", "product", "steak", "person")):
        roles.extend(["hero_subject", "supporting_subject", "narrative_payoff"])
    if any(token in haystack for token in ("object", "prop", "cutout", "foreground", "transparent")):
        roles.extend(["supporting_subject", "foreground_texture", "narrative_payoff"])
    if any(token in haystack for token in ("effect", "steam", "overlay", "atmospheric")):
        roles.extend(["atmospheric_layer", "motion_layer"])
    if "transition" in haystack:
        roles.append("transition_element")
    if any(token in haystack for token in ("hook", "caption", "subtitle", "text")):
        roles.append("caption_support")
    if any(token in haystack for token in ("logo", "brand", "marker")):
        roles.append("brand_marker")

    if not roles:
        if "video" in kind or media == "video":
            roles.extend(["motion_layer", "supporting_subject"])
        elif "audio" in media:
            roles.append("audio_layer")
        else:
            roles.extend(["supporting_subject", "foreground_texture"])

    return tuple(role for role in _dedupe(roles) if role in CINEMATIC_ROLES)


def _prompt_safe_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "title",
        "working_title",
        "description",
        "visual",
        "transparency",
        "compatibility",
        "source_type",
        "asset_pack_niche",
        "tags",
        "hook",
        "duration_seconds",
        "width",
        "height",
        "fps",
    }
    return {str(key): value for key, value in metadata.items() if str(key) in allowed_keys}


def _has_transparency(metadata: Mapping[str, Any]) -> bool:
    transparency = _mapping(metadata.get("transparency"))
    return bool(transparency.get("has_transparency"))


def _positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [text for text in (_optional_text(item) for item in value) if text is not None]


def _metadata_hints(metadata: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("title", "working_title", "description", "category", "pack_role", "asset_kind"):
        value = metadata.get(key)
        if isinstance(value, str):
            values.append(value)
    for key in ("tags", "intended_reel_formats"):
        value = metadata.get(key)
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            values.extend(str(item) for item in value)
    compatibility = metadata.get("compatibility")
    if isinstance(compatibility, Mapping):
        for value in compatibility.values():
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
                values.extend(str(item) for item in value)
    return values


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _required_text(value: Any, *, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field_name} is required")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None


def _first_text(*values: Any) -> str:
    for value in values:
        text = _optional_text(value)
        if text is not None:
            return text
    return "asset"


def _normalize(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", "_").split())


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


__all__ = [
    "CINEMATIC_ROLES",
    "CinematicAssetDescriptor",
    "cinematic_roles_for_asset",
    "normalize_asset_for_cinematic_planning",
]
