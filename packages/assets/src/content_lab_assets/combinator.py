"""Compatibility-aware asset pack combinator.

This module is intentionally deterministic: phase-1 callers can ask for candidate
reel compositions from an asset pack and get stable, explainable results without
needing historical metrics. Later phases can pass performance hints to weight the
same filtered candidates.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from itertools import product
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from content_lab_assets.compatibility import (
    AssetCompatibilityMetadata,
    CompatibilityDimension,
)
from content_lab_assets.types import AssetKind

ROLE_BACKGROUND = "background"
ROLE_FOREGROUND = "foreground"
ROLE_HOOK = "hook"
ROLE_AUDIO = "audio"
ROLE_EFFECT = "effect"
ROLE_FORMAT = "format"


class PackAsset(BaseModel):
    """An asset pack item reduced to the fields needed for composition."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    asset_kind: AssetKind
    pack_role: str | None = None
    title: str | None = None
    compatibility: AssetCompatibilityMetadata = Field(default_factory=AssetCompatibilityMetadata)
    metadata: dict[str, Any] = Field(default_factory=dict)
    performance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    usage_count: int = Field(default=0, ge=0)

    @classmethod
    def from_pack_item(cls, item: Mapping[str, Any]) -> PackAsset:
        metadata = _metadata_from_item(item)
        return cls(
            asset_id=str(item.get("asset_id") or item.get("id")),
            asset_kind=AssetKind(str(item["asset_kind"])),
            pack_role=_optional_text(item.get("pack_role") or item.get("role")),
            title=_optional_text(item.get("title") or item.get("working_title")),
            compatibility=AssetCompatibilityMetadata.from_metadata(metadata),
            metadata=metadata,
            performance_score=_optional_score(item.get("performance_score")),
            usage_count=max(0, int(item.get("usage_count") or 0)),
        )


class CandidateComposition(BaseModel):
    """A possible reel composition assembled from compatible pack assets."""

    model_config = ConfigDict(extra="forbid")

    composition_id: str
    roles: dict[str, PackAsset]
    compatibility_score: float = Field(ge=0.0, le=1.0)
    diversity_score: float = Field(ge=0.0, le=1.0)
    performance_score: float = Field(ge=0.0, le=1.0)
    selection_score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class OutputPotentialEstimate(BaseModel):
    """Estimate of how many useful reels a pack can support."""

    model_config = ConfigDict(extra="forbid")

    valid_combination_count: int
    useful_reel_capacity: int
    diversity: dict[str, int]
    bottlenecks: list[str]
    suggested_assets: list[str]


def generate_candidate_compositions(
    assets: Sequence[PackAsset | Mapping[str, Any]],
    *,
    target_reel_count: int,
    format_filters: Sequence[str] | None = None,
    style_filters: Sequence[str] | None = None,
    selection_mode: Literal["balanced", "exploit", "explore", "mutation", "chaos"] = "balanced",
) -> list[CandidateComposition]:
    """Create filtered, ranked, duplicate-free composition candidates."""

    if target_reel_count <= 0:
        raise ValueError("target_reel_count must be positive")
    pack_assets = [_coerce_pack_asset(asset) for asset in assets]
    filtered = [
        asset
        for asset in pack_assets
        if asset.compatibility.matches_filters(
            format_filters=format_filters,
            style_filters=style_filters,
        )
    ]
    buckets = _role_buckets(filtered)
    backgrounds = _optional_bucket(buckets, ROLE_BACKGROUND)
    foregrounds = _optional_bucket(buckets, ROLE_FOREGROUND)
    hooks = _optional_bucket(buckets, ROLE_HOOK)
    audio = _optional_bucket(buckets, ROLE_AUDIO)
    effects = _optional_bucket(buckets, ROLE_EFFECT)
    formats = _optional_bucket(buckets, ROLE_FORMAT)

    candidates: list[CandidateComposition] = []
    seen_ids: set[str] = set()
    for combo in product(backgrounds, foregrounds, hooks, audio, effects, formats):
        roles = _roles_from_combo(combo)
        if len(roles) < 2 or ROLE_HOOK not in roles:
            continue
        compatibility_score, reasons = _composition_compatibility(roles)
        if compatibility_score <= 0:
            continue
        composition_id = _composition_id(roles)
        if composition_id in seen_ids:
            continue
        seen_ids.add(composition_id)
        performance_score = _performance_score(roles.values())
        diversity_score = _diversity_score(roles.values())
        selection_score = _selection_score(
            compatibility_score=compatibility_score,
            diversity_score=diversity_score,
            performance_score=performance_score,
            average_usage=_average_usage(roles.values()),
            mode=selection_mode,
        )
        candidates.append(
            CandidateComposition(
                composition_id=composition_id,
                roles=roles,
                compatibility_score=compatibility_score,
                diversity_score=diversity_score,
                performance_score=performance_score,
                selection_score=selection_score,
                reasons=reasons,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate.selection_score,
            -candidate.compatibility_score,
            candidate.composition_id,
        ),
    )[:target_reel_count]


def estimate_output_potential(
    assets: Sequence[PackAsset | Mapping[str, Any]],
    *,
    target_reel_count: int | None = None,
    format_filters: Sequence[str] | None = None,
    style_filters: Sequence[str] | None = None,
) -> OutputPotentialEstimate:
    """Count valid combinations and identify the pack's weak spots."""

    pack_assets = [_coerce_pack_asset(asset) for asset in assets]
    candidates = generate_candidate_compositions(
        pack_assets,
        target_reel_count=10_000,
        format_filters=format_filters,
        style_filters=style_filters,
    )
    buckets = _role_buckets(pack_assets)
    diversity = {role: len(items) for role, items in sorted(buckets.items())}
    bottlenecks: list[str] = []
    suggestions: list[str] = []
    required_roles = {
        ROLE_BACKGROUND: "Add at least one background video or image.",
        ROLE_HOOK: "Add more hook text assets.",
        ROLE_AUDIO: "Add audio tracks with explicit moods.",
    }
    for role, suggestion in required_roles.items():
        count = diversity.get(role, 0)
        if count == 0:
            bottlenecks.append(f"no_{role}")
            suggestions.append(suggestion)
        elif count == 1 and role in {ROLE_BACKGROUND, ROLE_HOOK}:
            bottlenecks.append(f"low_{role}_diversity")
            suggestions.append(suggestion.replace("at least one ", "another "))
    if candidates and len(candidates) < (target_reel_count or 5):
        bottlenecks.append("limited_compatible_combinations")
        suggestions.append("Broaden compatibility tags across format, style, and audio mood.")

    useful_capacity = min(len(candidates), target_reel_count or len(candidates))
    return OutputPotentialEstimate(
        valid_combination_count=len(candidates),
        useful_reel_capacity=useful_capacity,
        diversity=diversity,
        bottlenecks=bottlenecks,
        suggested_assets=_dedupe_text(suggestions),
    )


def select_performance_weighted_combinations(
    assets: Sequence[PackAsset | Mapping[str, Any]],
    *,
    target_reel_count: int,
    format_filters: Sequence[str] | None = None,
    style_filters: Sequence[str] | None = None,
    mode: Literal["balanced", "exploit", "explore", "mutation", "chaos"] = "balanced",
) -> list[CandidateComposition]:
    """Rank compatible combinations with performance hints and cooldown-aware novelty."""

    return generate_candidate_compositions(
        assets,
        target_reel_count=target_reel_count,
        format_filters=format_filters,
        style_filters=style_filters,
        selection_mode=mode,
    )


def compatible_asset_pair(left: PackAsset, right: PackAsset) -> bool:
    """Return whether two assets can sensibly appear in the same composition."""

    score, _ = _pair_score(left, right)
    return score > 0


def _role_buckets(assets: Sequence[PackAsset]) -> dict[str, list[PackAsset]]:
    buckets: dict[str, list[PackAsset]] = {}
    for asset in assets:
        role = _role_for_asset(asset)
        buckets.setdefault(role, []).append(asset)
    return buckets


def _optional_bucket(
    buckets: Mapping[str, list[PackAsset]],
    role: str,
) -> list[PackAsset | None]:
    values = buckets.get(role, [])
    return list(values) if values else [None]


def _role_for_asset(asset: PackAsset) -> str:
    explicit_role = _optional_text(asset.pack_role)
    if explicit_role:
        lowered = explicit_role.lower()
        for role in (ROLE_BACKGROUND, ROLE_HOOK, ROLE_AUDIO, ROLE_EFFECT, ROLE_FORMAT):
            if role in lowered:
                return role
        if "object" in lowered or "subject" in lowered or "foreground" in lowered:
            return ROLE_FOREGROUND
    return {
        AssetKind.BACKGROUND_VIDEO: ROLE_BACKGROUND,
        AssetKind.BACKGROUND_IMAGE: ROLE_BACKGROUND,
        AssetKind.HOOK_TEXT: ROLE_HOOK,
        AssetKind.CAPTION_TEXT: ROLE_HOOK,
        AssetKind.AUDIO_TRACK: ROLE_AUDIO,
        AssetKind.SOUND_EFFECT: ROLE_AUDIO,
        AssetKind.VOICEOVER: ROLE_AUDIO,
        AssetKind.EFFECT_VIDEO: ROLE_EFFECT,
        AssetKind.EFFECT_IMAGE: ROLE_EFFECT,
        AssetKind.TRANSITION_LAYER: ROLE_EFFECT,
        AssetKind.DESIGN_TEMPLATE: ROLE_FORMAT,
        AssetKind.OVERLAY_PLAN: ROLE_FORMAT,
    }.get(asset.asset_kind, ROLE_FOREGROUND)


def _roles_from_combo(combo: tuple[PackAsset | None, ...]) -> dict[str, PackAsset]:
    role_names = [ROLE_BACKGROUND, ROLE_FOREGROUND, ROLE_HOOK, ROLE_AUDIO, ROLE_EFFECT, ROLE_FORMAT]
    return {role: asset for role, asset in zip(role_names, combo, strict=True) if asset is not None}


def _composition_compatibility(roles: Mapping[str, PackAsset]) -> tuple[float, list[str]]:
    assets = list(roles.values())
    if len({asset.asset_id for asset in assets}) != len(assets):
        return 0.0, ["duplicate asset in composition"]
    pair_scores: list[float] = []
    reasons: list[str] = []
    for index, left in enumerate(assets):
        for right in assets[index + 1 :]:
            score, reason = _pair_score(left, right)
            if score <= 0:
                return 0.0, [reason]
            pair_scores.append(score)
            if reason:
                reasons.append(reason)
    if not pair_scores:
        return 0.5, ["single compatible role"]
    return round(sum(pair_scores) / len(pair_scores), 4), _dedupe_text(reasons)


def _pair_score(left: PackAsset, right: PackAsset) -> tuple[float, str]:
    left_role = _role_for_asset(left)
    right_role = _role_for_asset(right)
    if left_role == ROLE_BACKGROUND and not _background_supports(left, right):
        return 0.0, "background does not support foreground/object type"
    if right_role == ROLE_BACKGROUND and not _background_supports(right, left):
        return 0.0, "background does not support foreground/object type"
    if left_role == ROLE_AUDIO and not _audio_supports(right, left):
        return 0.0, "audio mood is incompatible"
    if right_role == ROLE_AUDIO and not _audio_supports(left, right):
        return 0.0, "audio mood is incompatible"
    if left_role == ROLE_HOOK and not _hook_supports(right, left):
        return 0.0, "hook type is incompatible"
    if right_role == ROLE_HOOK and not _hook_supports(left, right):
        return 0.0, "hook type is incompatible"
    if not _transparency_safe(left) or not _transparency_safe(right):
        return 0.0, "asset requires transparency but is not a layerable kind"

    dimensions: tuple[CompatibilityDimension, ...] = (
        "niche",
        "topic",
        "theme",
        "emotion",
        "visual_style",
        "pace",
        "format_type",
    )
    matches = 0
    comparisons = 0
    for dimension in dimensions:
        left_values = set(getattr(left.compatibility, dimension))
        right_values = set(getattr(right.compatibility, dimension))
        if not left_values or not right_values:
            continue
        comparisons += 1
        if left_values.intersection(right_values):
            matches += 1
        else:
            return 0.0, f"{dimension} tags do not overlap"
    if comparisons == 0:
        return 0.72, "compatible by role defaults"
    return round(0.7 + (0.3 * matches / comparisons), 4), "compatible metadata overlap"


def _background_supports(background: PackAsset, asset: PackAsset) -> bool:
    if _role_for_asset(asset) not in {ROLE_FOREGROUND, ROLE_EFFECT}:
        return True
    allowed = set(background.compatibility.works_as_background_for)
    if not allowed:
        return True
    return bool(allowed.intersection(_asset_type_tokens(asset)))


def _audio_supports(asset: PackAsset, audio_asset: PackAsset) -> bool:
    moods = set(audio_asset.compatibility.emotion) | set(
        audio_asset.compatibility.works_with_audio_moods
    )
    if not asset.compatibility.works_with_audio_moods or not moods:
        return True
    return bool(set(asset.compatibility.works_with_audio_moods).intersection(moods))


def _hook_supports(asset: PackAsset, hook_asset: PackAsset) -> bool:
    hook_types = set(hook_asset.compatibility.theme) | set(hook_asset.compatibility.format_type)
    if not asset.compatibility.works_with_hook_types or not hook_types:
        return True
    return bool(set(asset.compatibility.works_with_hook_types).intersection(hook_types))


def _transparency_safe(asset: PackAsset) -> bool:
    if not asset.compatibility.requires_transparency:
        return True
    return asset.asset_kind in {
        AssetKind.TRANSPARENT_CUTOUT_PNG,
        AssetKind.MASKED_IMAGE,
        AssetKind.FOREGROUND_LAYER_IMAGE,
        AssetKind.FOREGROUND_LAYER_VIDEO,
    }


def _asset_type_tokens(asset: PackAsset) -> set[str]:
    tokens = {
        asset.asset_kind.value,
        _role_for_asset(asset),
    }
    if asset.pack_role:
        tokens.add(asset.pack_role.lower().replace(" ", "_"))
    tokens.update(asset.compatibility.works_with_object_types)
    return tokens


def _composition_id(roles: Mapping[str, PackAsset]) -> str:
    material = "|".join(f"{role}:{asset.asset_id}" for role, asset in sorted(roles.items()))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _performance_score(assets: Iterable[PackAsset]) -> float:
    scores = [
        0.5 if asset.performance_score is None else asset.performance_score for asset in assets
    ]
    if not scores:
        return 0.5
    return round(sum(scores) / len(scores), 4)


def _diversity_score(assets: Iterable[PackAsset]) -> float:
    asset_list = list(assets)
    if not asset_list:
        return 0.0
    unique_styles: set[str] = set()
    unique_formats: set[str] = set()
    for asset in asset_list:
        unique_styles.update(asset.compatibility.visual_style)
        unique_formats.update(asset.compatibility.format_type)
    return round(min(1.0, (len(unique_styles) + len(unique_formats) + len(asset_list)) / 8), 4)


def _average_usage(assets: Iterable[PackAsset]) -> float:
    usage = [asset.usage_count for asset in assets]
    return 0.0 if not usage else sum(usage) / len(usage)


def _selection_score(
    *,
    compatibility_score: float,
    diversity_score: float,
    performance_score: float,
    average_usage: float,
    mode: Literal["balanced", "exploit", "explore", "mutation", "chaos"],
) -> float:
    cooldown_penalty = min(0.25, average_usage * 0.04)
    weights = {
        "balanced": (0.45, 0.25, 0.30),
        "exploit": (0.30, 0.10, 0.60),
        "explore": (0.35, 0.50, 0.15),
        "mutation": (0.40, 0.40, 0.20),
        "chaos": (0.20, 0.65, 0.15),
    }[mode]
    score = (
        compatibility_score * weights[0]
        + diversity_score * weights[1]
        + performance_score * weights[2]
        - cooldown_penalty
    )
    return round(max(0.0, min(1.0, score)), 4)


def _metadata_from_item(item: Mapping[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    if isinstance(metadata, Mapping):
        return dict(metadata)
    metadata_json = item.get("metadata_json")
    if isinstance(metadata_json, Mapping):
        return dict(metadata_json)
    return {
        key: value
        for key, value in item.items()
        if key in AssetCompatibilityMetadata.model_fields
        or key in {"compatibility", "compatible_with"}
    }


def _coerce_pack_asset(asset: PackAsset | Mapping[str, Any]) -> PackAsset:
    return asset if isinstance(asset, PackAsset) else PackAsset.from_pack_item(asset)


def _token_set(values: Sequence[str]) -> set[str]:
    return {token for value in values if (token := _normalize_token(value)) is not None}


def _normalize_token(value: Any) -> str | None:
    normalized = "_".join(str(value).strip().lower().replace("-", "_").split())
    return normalized or None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None


def _optional_score(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return max(0.0, min(1.0, float(value)))


def _dedupe_text(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


__all__ = [
    "AssetCompatibilityMetadata",
    "CandidateComposition",
    "OutputPotentialEstimate",
    "PackAsset",
    "compatible_asset_pair",
    "estimate_output_potential",
    "generate_candidate_compositions",
    "select_performance_weighted_combinations",
]
