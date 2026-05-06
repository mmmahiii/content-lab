"""Deterministic planning for reusable asset packs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import floor
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from content_lab_assets.combinator import AssetCompatibilityMetadata
from content_lab_assets.types import AssetKind, MediaType, infer_media_type_for_asset_kind

DEFAULT_REEL_FORMATS = [
    "hook-led tip",
    "before-after transformation",
    "mistake-fix explainer",
    "step-by-step demo",
    "saveable checklist",
]

DEFAULT_ASSET_WEIGHTS: Mapping[AssetKind, float] = {
    AssetKind.BACKGROUND_VIDEO: 0.26,
    AssetKind.SUBJECT_VIDEO: 0.22,
    AssetKind.PROP_IMAGE: 0.16,
    AssetKind.TRANSPARENT_CUTOUT_PNG: 0.14,
    AssetKind.EFFECT_VIDEO: 0.10,
    AssetKind.HOOK_TEXT: 0.07,
    AssetKind.AUDIO_TRACK: 0.05,
}

OUTPUT_POTENTIAL_CRITERIA = [
    "reuse_potential",
    "combination_potential",
    "visual_flexibility",
    "niche_relevance",
    "realism_support",
    "format_coverage",
    "cost_saving_potential",
    "novelty_without_bloat",
]

OUTPUT_POTENTIAL_WEIGHTS: Mapping[str, float] = {
    "reuse_potential": 0.18,
    "combination_potential": 0.20,
    "visual_flexibility": 0.14,
    "niche_relevance": 0.12,
    "realism_support": 0.12,
    "format_coverage": 0.10,
    "cost_saving_potential": 0.09,
    "novelty_without_bloat": 0.05,
}

ASSET_KIND_CATEGORY: Mapping[AssetKind, str] = {
    AssetKind.BACKGROUND_VIDEO: "scene_setter",
    AssetKind.SUBJECT_VIDEO: "proof_visual",
    AssetKind.PROP_IMAGE: "detail_prop",
    AssetKind.TRANSPARENT_CUTOUT_PNG: "layerable_cutout",
    AssetKind.EFFECT_VIDEO: "transition_motif",
    AssetKind.HOOK_TEXT: "hook_copy",
    AssetKind.AUDIO_TRACK: "audio_bed",
    AssetKind.BACKGROUND_IMAGE: "scene_setter",
    AssetKind.SUBJECT_IMAGE: "proof_visual",
    AssetKind.OBJECT_IMAGE: "detail_prop",
    AssetKind.OBJECT_VIDEO: "proof_visual",
    AssetKind.PROP_VIDEO: "detail_prop",
    AssetKind.FOREGROUND_LAYER_IMAGE: "layerable_cutout",
    AssetKind.FOREGROUND_LAYER_VIDEO: "transition_motif",
    AssetKind.OVERLAY_PLAN: "overlay_system",
    AssetKind.CAPTION_TEXT: "caption_copy",
    AssetKind.DESIGN_TEMPLATE: "layout_system",
    AssetKind.SOUND_EFFECT: "audio_accent",
    AssetKind.VOICEOVER: "voiceover",
}

ASSET_CATEGORY_DEFAULT_KIND: Mapping[str, AssetKind] = {
    "scene_setter": AssetKind.BACKGROUND_VIDEO,
    "proof_visual": AssetKind.SUBJECT_VIDEO,
    "detail_prop": AssetKind.PROP_IMAGE,
    "layerable_cutout": AssetKind.TRANSPARENT_CUTOUT_PNG,
    "transition_motif": AssetKind.EFFECT_VIDEO,
    "hook_copy": AssetKind.HOOK_TEXT,
    "audio_bed": AssetKind.AUDIO_TRACK,
    "overlay_system": AssetKind.OVERLAY_PLAN,
    "caption_copy": AssetKind.CAPTION_TEXT,
    "layout_system": AssetKind.DESIGN_TEMPLATE,
    "audio_accent": AssetKind.SOUND_EFFECT,
    "voiceover": AssetKind.VOICEOVER,
}

ASSET_MIX_ALIASES: Mapping[str, AssetKind] = {
    "background": AssetKind.BACKGROUND_VIDEO,
    "backgrounds": AssetKind.BACKGROUND_VIDEO,
    "object": AssetKind.PROP_IMAGE,
    "objects": AssetKind.PROP_IMAGE,
    "object_prop": AssetKind.PROP_IMAGE,
    "object_props": AssetKind.PROP_IMAGE,
    "prop": AssetKind.PROP_IMAGE,
    "props": AssetKind.PROP_IMAGE,
    "subject": AssetKind.SUBJECT_VIDEO,
    "subjects": AssetKind.SUBJECT_VIDEO,
    "foreground": AssetKind.TRANSPARENT_CUTOUT_PNG,
    "foregrounds": AssetKind.TRANSPARENT_CUTOUT_PNG,
    "subject_foreground": AssetKind.SUBJECT_VIDEO,
    "subject_foregrounds": AssetKind.SUBJECT_VIDEO,
    "cutout": AssetKind.TRANSPARENT_CUTOUT_PNG,
    "cutouts": AssetKind.TRANSPARENT_CUTOUT_PNG,
    "hook": AssetKind.HOOK_TEXT,
    "hooks": AssetKind.HOOK_TEXT,
    "audio": AssetKind.AUDIO_TRACK,
    "audio_mood": AssetKind.AUDIO_TRACK,
    "audio_moods": AssetKind.AUDIO_TRACK,
    "format": AssetKind.DESIGN_TEMPLATE,
    "formats": AssetKind.DESIGN_TEMPLATE,
    "effect": AssetKind.EFFECT_VIDEO,
    "effects": AssetKind.EFFECT_VIDEO,
    "format_effect": AssetKind.EFFECT_VIDEO,
    "format_effects": AssetKind.EFFECT_VIDEO,
}

CATEGORY_OUTPUT_POTENTIAL_BASE: Mapping[str, Mapping[str, float]] = {
    "scene_setter": {
        "reuse_potential": 9.0,
        "combination_potential": 9.0,
        "visual_flexibility": 9.0,
        "niche_relevance": 8.0,
        "realism_support": 9.0,
        "format_coverage": 8.0,
        "cost_saving_potential": 9.0,
        "novelty_without_bloat": 8.0,
    },
    "proof_visual": {
        "reuse_potential": 8.0,
        "combination_potential": 8.0,
        "visual_flexibility": 8.0,
        "niche_relevance": 9.0,
        "realism_support": 9.0,
        "format_coverage": 7.0,
        "cost_saving_potential": 8.0,
        "novelty_without_bloat": 8.0,
    },
    "detail_prop": {
        "reuse_potential": 7.0,
        "combination_potential": 8.0,
        "visual_flexibility": 8.0,
        "niche_relevance": 8.0,
        "realism_support": 7.0,
        "format_coverage": 6.0,
        "cost_saving_potential": 7.0,
        "novelty_without_bloat": 8.0,
    },
    "layerable_cutout": {
        "reuse_potential": 8.0,
        "combination_potential": 9.0,
        "visual_flexibility": 9.0,
        "niche_relevance": 8.0,
        "realism_support": 8.0,
        "format_coverage": 7.0,
        "cost_saving_potential": 8.0,
        "novelty_without_bloat": 8.0,
    },
    "transition_motif": {
        "reuse_potential": 6.0,
        "combination_potential": 7.0,
        "visual_flexibility": 7.0,
        "niche_relevance": 6.0,
        "realism_support": 7.0,
        "format_coverage": 7.0,
        "cost_saving_potential": 6.0,
        "novelty_without_bloat": 7.0,
    },
    "hook_copy": {
        "reuse_potential": 7.0,
        "combination_potential": 9.0,
        "visual_flexibility": 6.0,
        "niche_relevance": 9.0,
        "realism_support": 6.0,
        "format_coverage": 9.0,
        "cost_saving_potential": 8.0,
        "novelty_without_bloat": 8.0,
    },
    "audio_bed": {
        "reuse_potential": 8.0,
        "combination_potential": 8.0,
        "visual_flexibility": 7.0,
        "niche_relevance": 7.0,
        "realism_support": 8.0,
        "format_coverage": 8.0,
        "cost_saving_potential": 8.0,
        "novelty_without_bloat": 7.0,
    },
    "overlay_system": {
        "reuse_potential": 7.0,
        "combination_potential": 7.0,
        "visual_flexibility": 6.0,
        "niche_relevance": 7.0,
        "realism_support": 6.0,
        "format_coverage": 8.0,
        "cost_saving_potential": 7.0,
        "novelty_without_bloat": 6.0,
    },
    "caption_copy": {
        "reuse_potential": 5.0,
        "combination_potential": 6.0,
        "visual_flexibility": 5.0,
        "niche_relevance": 8.0,
        "realism_support": 5.0,
        "format_coverage": 6.0,
        "cost_saving_potential": 6.0,
        "novelty_without_bloat": 6.0,
    },
    "layout_system": {
        "reuse_potential": 8.0,
        "combination_potential": 8.0,
        "visual_flexibility": 7.0,
        "niche_relevance": 7.0,
        "realism_support": 7.0,
        "format_coverage": 9.0,
        "cost_saving_potential": 9.0,
        "novelty_without_bloat": 7.0,
    },
    "audio_accent": {
        "reuse_potential": 6.0,
        "combination_potential": 7.0,
        "visual_flexibility": 6.0,
        "niche_relevance": 6.0,
        "realism_support": 7.0,
        "format_coverage": 6.0,
        "cost_saving_potential": 6.0,
        "novelty_without_bloat": 6.0,
    },
    "voiceover": {
        "reuse_potential": 5.0,
        "combination_potential": 5.0,
        "visual_flexibility": 4.0,
        "niche_relevance": 9.0,
        "realism_support": 8.0,
        "format_coverage": 5.0,
        "cost_saving_potential": 5.0,
        "novelty_without_bloat": 5.0,
    },
}


class AssetPackPlannedSpec(BaseModel):
    """One planned asset specification before any generation starts."""

    model_config = ConfigDict(extra="forbid")

    asset_kind: AssetKind
    media_type: MediaType
    category: str = Field(min_length=1, max_length=128)
    working_title: str = Field(min_length=1, max_length=256)
    purpose: str = Field(min_length=1)
    prompt_or_description: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    required_traits: dict[str, Any] = Field(default_factory=dict)
    compatible_with: dict[str, Any] = Field(default_factory=dict)
    compatibility: AssetCompatibilityMetadata = Field(default_factory=AssetCompatibilityMetadata)
    intended_reel_formats: list[str] = Field(default_factory=list)
    priority: int = Field(ge=0)
    estimated_reuse_count: int = Field(ge=0)
    output_potential_score: float = Field(ge=0, le=100)
    output_potential_scores: dict[str, float] = Field(default_factory=dict)
    output_potential_rationale: list[str] = Field(default_factory=list)


class OutputPotentialScore(BaseModel):
    """Deterministic score for how much one planned asset can unlock future reels."""

    model_config = ConfigDict(extra="forbid")

    total_score: float = Field(ge=0, le=100)
    criteria_scores: dict[str, float]
    rationale: list[str]


class AssetPackPlan(BaseModel):
    """Complete plan payload used by API and future generation workers."""

    model_config = ConfigDict(extra="forbid")

    asset_pack_plan: dict[str, Any]
    asset_mix: dict[str, int]
    planned_asset_specs: list[AssetPackPlannedSpec]
    strategy_summary: str = Field(min_length=1)
    reuse_rationale: str = Field(min_length=1)
    expected_reel_formats: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_pack_size(self) -> AssetPackPlan:
        requested_count = int(self.asset_pack_plan["requested_asset_count"])
        if len(self.planned_asset_specs) != requested_count:
            raise ValueError("planned_asset_specs must match requested_asset_count")
        if sum(self.asset_mix.values()) != requested_count:
            raise ValueError("asset_mix must match requested_asset_count")
        return self


class AssetPackPlanInput(BaseModel):
    """Inputs accepted by the asset pack planner."""

    model_config = ConfigDict(extra="forbid")

    niche: str = Field(min_length=1, max_length=256)
    target_audience: str | None = None
    requested_asset_count: int = Field(ge=1)
    asset_mix: dict[str, int] | None = None
    target_reel_types: list[str] = Field(default_factory=list)
    style_persona_constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("niche", mode="before")
    @classmethod
    def _normalize_niche(cls, value: str) -> str:
        return _normalize_text(value, field_name="niche", max_length=256)

    @field_validator("target_audience", mode="before")
    @classmethod
    def _normalize_target_audience(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name="target_audience", max_length=256)

    @field_validator("target_reel_types", mode="before")
    @classmethod
    def _normalize_reel_types(cls, value: Sequence[str] | None) -> list[str]:
        if value is None:
            return []
        return [
            _normalize_text(item, field_name="target_reel_types", max_length=96) for item in value
        ]

    @model_validator(mode="after")
    def _validate_asset_mix(self) -> AssetPackPlanInput:
        self.asset_mix = validate_requested_asset_mix(
            self.asset_mix,
            requested_asset_count=self.requested_asset_count,
        )
        return self


def generate_asset_pack_plan(
    *,
    niche: str,
    requested_asset_count: int,
    asset_mix: Mapping[str, int] | None = None,
    target_audience: str | None = None,
    target_reel_types: Sequence[str] | None = None,
    style_persona_constraints: Mapping[str, Any] | None = None,
) -> AssetPackPlan:
    """Generate a reusable pack plan before any asset generation begins."""

    plan_input = AssetPackPlanInput(
        niche=niche,
        target_audience=target_audience,
        requested_asset_count=requested_asset_count,
        asset_mix=None if asset_mix is None else dict(asset_mix),
        target_reel_types=list(target_reel_types or []),
        style_persona_constraints=dict(style_persona_constraints or {}),
    )
    final_mix = _resolve_asset_mix(plan_input.asset_mix, plan_input.requested_asset_count)
    mix_guidance = _asset_mix_guidance(final_mix, plan_input.requested_asset_count)
    expected_reel_formats = plan_input.target_reel_types or list(DEFAULT_REEL_FORMATS)
    planned_specs = _build_planned_specs(
        niche=plan_input.niche,
        asset_mix=final_mix,
        expected_reel_formats=expected_reel_formats,
        style_persona_constraints=plan_input.style_persona_constraints,
    )
    mix_was_defaulted = plan_input.asset_mix is None
    pack_strategy = _build_pack_strategy(
        niche=plan_input.niche,
        target_audience=plan_input.target_audience,
        requested_asset_count=plan_input.requested_asset_count,
        asset_mix=final_mix,
        expected_reel_formats=expected_reel_formats,
        style_persona_constraints=plan_input.style_persona_constraints,
        planned_specs=planned_specs,
    )
    strategy_summary = _build_strategy_summary(
        pack_strategy=pack_strategy,
    )
    reuse_rationale = (
        f"This pack gives {plan_input.niche} reels reusable scene context, proof visuals, "
        "layerable details, and pacing assets so future reels can recombine the same library "
        "without repeating one complete generated clip."
    )
    asset_pack_plan = {
        "niche": plan_input.niche,
        "target_audience": plan_input.target_audience,
        "requested_asset_count": plan_input.requested_asset_count,
        "asset_mix_source": "default" if mix_was_defaulted else "requested",
        "target_reel_types": expected_reel_formats,
        "style_persona_constraints": plan_input.style_persona_constraints,
        "pack_strategy": pack_strategy,
        "category_rationale": _category_rationale(final_mix),
        "output_potential_scoring": _output_potential_scoring_summary(planned_specs),
    }
    if mix_guidance:
        asset_pack_plan["asset_mix_guidance"] = mix_guidance

    return AssetPackPlan(
        asset_pack_plan=asset_pack_plan,
        asset_mix=final_mix,
        planned_asset_specs=planned_specs,
        strategy_summary=strategy_summary,
        reuse_rationale=reuse_rationale,
        expected_reel_formats=expected_reel_formats,
    )


def validate_requested_asset_mix(
    requested_mix: Mapping[str, int] | None,
    *,
    requested_asset_count: int,
) -> dict[str, int] | None:
    """Validate and normalize an operator-provided exact asset mix."""

    if requested_mix is None:
        return None
    normalized: dict[str, int] = {}
    for raw_kind, raw_count in requested_mix.items():
        kind = _asset_mix_key_to_kind(raw_kind)
        if raw_count < 0:
            raise ValueError("asset_mix counts must be nonnegative")
        if raw_count > 0:
            normalized[kind.value] = normalized.get(kind.value, 0) + int(raw_count)
    if not normalized:
        raise ValueError("asset_mix must include at least one positive count")

    requested_mix_total = sum(normalized.values())
    if requested_mix_total != requested_asset_count:
        raise ValueError(
            "asset_mix total must equal requested_asset_count; "
            f"got asset_mix total {requested_mix_total} for requested_asset_count "
            f"{requested_asset_count}. Provide only requested_asset_count to let the system "
            "propose a split, or adjust the asset_mix counts."
        )
    return normalized


def _resolve_asset_mix(
    requested_mix: dict[str, int] | None,
    requested_asset_count: int,
) -> dict[str, int]:
    if requested_mix is None:
        return _weighted_counts(DEFAULT_ASSET_WEIGHTS, requested_asset_count)

    return dict(requested_mix)


def _asset_mix_key_to_kind(raw_key: str) -> AssetKind:
    normalized_key = _normalize_mix_key(raw_key)
    try:
        return AssetKind(normalized_key)
    except ValueError:
        pass
    if normalized_key in ASSET_CATEGORY_DEFAULT_KIND:
        return ASSET_CATEGORY_DEFAULT_KIND[normalized_key]
    if normalized_key in ASSET_MIX_ALIASES:
        return ASSET_MIX_ALIASES[normalized_key]
    valid_categories = ", ".join(sorted(ASSET_CATEGORY_DEFAULT_KIND))
    valid_kinds = ", ".join(sorted(kind.value for kind in AssetKind))
    raise ValueError(
        f"asset_mix key '{raw_key}' is not a supported asset kind or category. "
        f"Use an AssetKind value such as {AssetKind.BACKGROUND_VIDEO.value!r}, "
        f"or a category such as 'scene_setter'. Supported categories: "
        f"{valid_categories}. Supported kinds: {valid_kinds}."
    )


def _normalize_mix_key(raw_key: str) -> str:
    return str(raw_key).strip().lower().replace("/", "_").replace("-", "_").replace(" ", "_")


def _asset_mix_guidance(asset_mix: Mapping[str, int], requested_asset_count: int) -> list[str]:
    guidance: list[str] = []
    positive_kind_count = len([count for count in asset_mix.values() if count > 0])
    if requested_asset_count >= 6 and positive_kind_count < 3:
        guidance.append(
            "This mix is narrow for the requested pack size. Consider adding scene, proof, "
            "detail, hook, and audio assets so the pack can unlock more reel formats."
        )
    largest_count = max(asset_mix.values(), default=0)
    if requested_asset_count >= 10 and largest_count / requested_asset_count > 0.6:
        guidance.append(
            "One asset kind dominates the pack. Consider spreading counts across complementary "
            "categories to improve reuse and reduce repetitive outputs."
        )
    return guidance


def _weighted_counts(weights: Mapping[AssetKind, float], total: int) -> dict[str, int]:
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        raise ValueError("asset mix weights must sum to a positive value")

    raw = {kind: (weight / weight_sum) * total for kind, weight in weights.items()}
    counts = {kind: floor(value) for kind, value in raw.items()}
    remaining = total - sum(counts.values())
    ranked = sorted(
        raw,
        key=lambda kind: (raw[kind] - counts[kind], weights[kind], kind.value),
        reverse=True,
    )
    for kind in ranked[:remaining]:
        counts[kind] += 1
    return {kind.value: count for kind, count in counts.items() if count > 0}


def _build_planned_specs(
    *,
    niche: str,
    asset_mix: Mapping[str, int],
    expected_reel_formats: list[str],
    style_persona_constraints: Mapping[str, Any],
) -> list[AssetPackPlannedSpec]:
    specs: list[AssetPackPlannedSpec] = []
    style_note = _style_note(style_persona_constraints)
    category_seen_counts: dict[str, int] = {}
    for raw_kind, count in asset_mix.items():
        kind = AssetKind(raw_kind)
        category = ASSET_KIND_CATEGORY.get(kind, kind.value)
        for index in range(1, count + 1):
            category_seen_counts[category] = category_seen_counts.get(category, 0) + 1
            output_potential = _score_output_potential(
                category=category,
                kind=kind,
                category_index=category_seen_counts[category],
                expected_reel_formats=expected_reel_formats,
                style_persona_constraints=style_persona_constraints,
            )
            compatibility = _compatibility_metadata(
                niche=niche,
                category=category,
                expected_reel_formats=expected_reel_formats,
                style_persona_constraints=style_persona_constraints,
            )
            specs.append(
                AssetPackPlannedSpec(
                    asset_kind=kind,
                    media_type=infer_media_type_for_asset_kind(kind),
                    category=category,
                    working_title=_working_title(niche, category, index),
                    purpose=_purpose(niche, category, expected_reel_formats),
                    prompt_or_description=_prompt(niche, category, kind, index, style_note),
                    rationale=_rationale(category),
                    required_traits=_required_traits(
                        category,
                        style_persona_constraints,
                        output_potential=output_potential,
                    ),
                    compatible_with={
                        "niche": niche,
                        "reel_formats": expected_reel_formats,
                        "style_persona_constraints": dict(style_persona_constraints),
                    },
                    compatibility=compatibility,
                    intended_reel_formats=_formats_for_category(category, expected_reel_formats),
                    priority=0,
                    estimated_reuse_count=_estimated_reuse_count(
                        output_potential.total_score,
                        expected_reel_formats,
                    ),
                    output_potential_score=output_potential.total_score,
                    output_potential_scores=output_potential.criteria_scores,
                    output_potential_rationale=output_potential.rationale,
                )
            )
    return _prioritize_specs_by_output_potential(specs)


def _score_output_potential(
    *,
    category: str,
    kind: AssetKind,
    category_index: int,
    expected_reel_formats: list[str],
    style_persona_constraints: Mapping[str, Any],
) -> OutputPotentialScore:
    base_scores = dict(
        CATEGORY_OUTPUT_POTENTIAL_BASE.get(
            category,
            {criterion: 5.0 for criterion in OUTPUT_POTENTIAL_CRITERIA},
        )
    )
    intended_formats = _formats_for_category(category, expected_reel_formats)
    if expected_reel_formats:
        format_ratio = len(intended_formats) / len(expected_reel_formats)
        base_scores["format_coverage"] = max(
            base_scores["format_coverage"],
            round(5.0 + (format_ratio * 5.0), 2),
        )
    if style_persona_constraints and category in {
        "scene_setter",
        "proof_visual",
        "detail_prop",
        "layerable_cutout",
        "hook_copy",
    }:
        base_scores["niche_relevance"] = min(10.0, base_scores["niche_relevance"] + 0.5)
    if infer_media_type_for_asset_kind(kind) is MediaType.VIDEO and category in {
        "scene_setter",
        "proof_visual",
        "transition_motif",
    }:
        base_scores["realism_support"] = min(10.0, base_scores["realism_support"] + 0.5)

    duplicate_penalty = max(0, category_index - 2) * 0.7
    base_scores["novelty_without_bloat"] = max(
        2.0,
        base_scores["novelty_without_bloat"] - duplicate_penalty,
    )
    if category_index >= 5:
        base_scores["combination_potential"] = max(
            4.0,
            base_scores["combination_potential"] - 0.3 * (category_index - 4),
        )

    criteria_scores = {
        criterion: round(base_scores[criterion], 2) for criterion in OUTPUT_POTENTIAL_CRITERIA
    }
    weighted_score = sum(
        criteria_scores[criterion] * OUTPUT_POTENTIAL_WEIGHTS[criterion]
        for criterion in criteria_scores
    )
    total_score = round(weighted_score * 10, 2)
    return OutputPotentialScore(
        total_score=total_score,
        criteria_scores=criteria_scores,
        rationale=_output_potential_rationale(
            category=category,
            criteria_scores=criteria_scores,
            category_index=category_index,
        ),
    )


def _output_potential_rationale(
    *,
    category: str,
    criteria_scores: Mapping[str, float],
    category_index: int,
) -> list[str]:
    readable_category = category.replace("_", " ")
    strongest = sorted(
        criteria_scores,
        key=lambda criterion: (criteria_scores[criterion], criterion),
        reverse=True,
    )[:3]
    rationale = [
        f"High-priority {readable_category} asset because it scores strongly for "
        f"{', '.join(criterion.replace('_', ' ') for criterion in strongest)}."
    ]
    if criteria_scores["combination_potential"] >= 8:
        rationale.append("Can combine with many backgrounds, hooks, audio beds, or proof beats.")
    if criteria_scores["cost_saving_potential"] >= 8:
        rationale.append("Reduces future generation cost by acting as reusable source material.")
    if category_index >= 3:
        rationale.append(
            "Later item in this category, so novelty-without-bloat is discounted to avoid filler."
        )
    return rationale


def _prioritize_specs_by_output_potential(
    specs: list[AssetPackPlannedSpec],
) -> list[AssetPackPlannedSpec]:
    ordered = sorted(
        specs,
        key=lambda spec: (
            -spec.output_potential_score,
            spec.category,
            spec.asset_kind.value,
            spec.working_title,
        ),
    )
    for priority, spec in enumerate(ordered):
        spec.priority = priority
    return ordered


def _estimated_reuse_count(
    output_potential_score: float,
    expected_reel_formats: list[str],
) -> int:
    base = len(expected_reel_formats) + 1
    if output_potential_score >= 85:
        base += 2
    elif output_potential_score >= 75:
        base += 1
    return max(2, min(10, base))


def _output_potential_scoring_summary(
    planned_specs: Sequence[AssetPackPlannedSpec],
) -> dict[str, Any]:
    top_specs = planned_specs[: min(5, len(planned_specs))]
    return {
        "criteria": list(OUTPUT_POTENTIAL_CRITERIA),
        "weights": dict(OUTPUT_POTENTIAL_WEIGHTS),
        "priority_method": "weighted_output_potential_desc",
        "top_priority_assets": [
            {
                "priority": spec.priority,
                "asset_kind": spec.asset_kind.value,
                "category": spec.category,
                "working_title": spec.working_title,
                "output_potential_score": spec.output_potential_score,
                "rationale": spec.output_potential_rationale,
            }
            for spec in top_specs
        ],
    }


def _build_pack_strategy(
    *,
    niche: str,
    target_audience: str | None,
    requested_asset_count: int,
    asset_mix: Mapping[str, int],
    expected_reel_formats: list[str],
    style_persona_constraints: Mapping[str, Any],
    planned_specs: Sequence[AssetPackPlannedSpec],
) -> dict[str, Any]:
    category_split = _asset_category_split(asset_mix)
    top_specs = planned_specs[: min(5, len(planned_specs))]
    return {
        "niche": niche,
        "target_audience": target_audience or "Operators can refine this before generation.",
        "visual_style": _visual_style_summary(style_persona_constraints),
        "emotional_angles": _emotional_angles(
            niche, expected_reel_formats, style_persona_constraints
        ),
        "core_motifs": _core_motifs(niche, category_split, style_persona_constraints),
        "asset_category_split": category_split,
        "expected_reel_formats": expected_reel_formats,
        "why_these_assets_were_chosen": _why_assets_were_chosen(top_specs),
        "multi_reel_generation_strategy": _multi_reel_generation_strategy(
            category_split,
            expected_reel_formats,
            requested_asset_count,
        ),
    }


def _build_strategy_summary(*, pack_strategy: Mapping[str, Any]) -> str:
    split_text = ", ".join(
        f"{category.replace('_', ' ')}: {count}"
        for category, count in pack_strategy["asset_category_split"].items()
    )
    angle_text = ", ".join(pack_strategy["emotional_angles"])
    motif_text = ", ".join(pack_strategy["core_motifs"])
    format_text = ", ".join(pack_strategy["expected_reel_formats"])
    chosen_text = " ".join(pack_strategy["why_these_assets_were_chosen"])
    return (
        f"Asset pack strategy for {pack_strategy['niche']} targeting "
        f"{pack_strategy['target_audience']}. Visual style: "
        f"{pack_strategy['visual_style']}. Emotional angles: {angle_text}. "
        f"Core motifs: {motif_text}. Category split: {split_text}. "
        f"Expected reel formats: {format_text}. Why these assets: {chosen_text} "
        f"Multi-reel plan: {pack_strategy['multi_reel_generation_strategy']}"
    ).strip()


def _category_rationale(asset_mix: Mapping[str, int]) -> dict[str, str]:
    rationale: dict[str, str] = {}
    for raw_kind in asset_mix:
        kind = AssetKind(raw_kind)
        category = ASSET_KIND_CATEGORY.get(kind, kind.value)
        rationale[category] = _rationale(category)
    return rationale


def _asset_category_split(asset_mix: Mapping[str, int]) -> dict[str, int]:
    split: dict[str, int] = {}
    for raw_kind, count in asset_mix.items():
        kind = AssetKind(raw_kind)
        category = ASSET_KIND_CATEGORY.get(kind, kind.value)
        split[category] = split.get(category, 0) + count
    return dict(sorted(split.items()))


def _visual_style_summary(style_persona_constraints: Mapping[str, Any]) -> str:
    if not style_persona_constraints:
        return "Flexible platform-native vertical style with clean framing and caption-safe space."
    preferred_keys = [
        "visual_style",
        "style",
        "palette",
        "tone",
        "persona",
        "lighting",
        "camera",
    ]
    selected = [
        f"{key}: {style_persona_constraints[key]}"
        for key in preferred_keys
        if key in style_persona_constraints
    ]
    if not selected:
        selected = [
            f"{key}: {value}" for key, value in sorted(style_persona_constraints.items())[:4]
        ]
    return "; ".join(selected)


def _emotional_angles(
    niche: str,
    expected_reel_formats: list[str],
    style_persona_constraints: Mapping[str, Any],
) -> list[str]:
    if "emotional_angles" in style_persona_constraints:
        raw_angles = style_persona_constraints["emotional_angles"]
        if isinstance(raw_angles, str):
            return [_normalize_text(raw_angles, field_name="emotional_angles", max_length=128)]
        if isinstance(raw_angles, Sequence):
            return [
                _normalize_text(str(angle), field_name="emotional_angles", max_length=128)
                for angle in raw_angles[:4]
            ]
    angles = [
        f"make {niche} feel immediately attainable",
        "show proof before asking for trust",
        "turn small habits into visible progress",
    ]
    if any("mistake" in reel_format.lower() for reel_format in expected_reel_formats):
        angles.append("relieve frustration by naming common mistakes")
    elif any("before" in reel_format.lower() for reel_format in expected_reel_formats):
        angles.append("create transformation tension between before and after states")
    else:
        angles.append("build curiosity through fast, useful contrast")
    return angles[:4]


def _core_motifs(
    niche: str,
    category_split: Mapping[str, int],
    style_persona_constraints: Mapping[str, Any],
) -> list[str]:
    if "core_motifs" in style_persona_constraints:
        raw_motifs = style_persona_constraints["core_motifs"]
        if isinstance(raw_motifs, str):
            return [_normalize_text(raw_motifs, field_name="core_motifs", max_length=128)]
        if isinstance(raw_motifs, Sequence):
            return [
                _normalize_text(str(motif), field_name="core_motifs", max_length=128)
                for motif in raw_motifs[:5]
            ]
    motifs = [
        f"{niche} scene context",
        "caption-safe negative space",
    ]
    if "proof_visual" in category_split:
        motifs.append("demonstration and payoff beats")
    if "detail_prop" in category_split or "layerable_cutout" in category_split:
        motifs.append("specific props and foreground details")
    if "hook_copy" in category_split:
        motifs.append("reusable hook language")
    if "audio_bed" in category_split:
        motifs.append("recognizable audio mood")
    return motifs[:5]


def _why_assets_were_chosen(planned_specs: Sequence[AssetPackPlannedSpec]) -> list[str]:
    if not planned_specs:
        return ["No planned specs were produced."]
    reasons: list[str] = []
    seen_categories: set[str] = set()
    for spec in planned_specs:
        if spec.category in seen_categories:
            continue
        seen_categories.add(spec.category)
        rationale = (
            spec.output_potential_rationale[0]
            if spec.output_potential_rationale
            else spec.rationale
        )
        reasons.append(
            f"{spec.category.replace('_', ' ')} assets lead with score "
            f"{spec.output_potential_score:g}: {rationale}"
        )
    return reasons


def _multi_reel_generation_strategy(
    category_split: Mapping[str, int],
    expected_reel_formats: list[str],
    requested_asset_count: int,
) -> str:
    visual_categories = [
        category
        for category in ("scene_setter", "proof_visual", "detail_prop", "layerable_cutout")
        if category in category_split
    ]
    pacing_categories = [
        category
        for category in ("hook_copy", "audio_bed", "transition_motif", "layout_system")
        if category in category_split
    ]
    visual_text = (
        ", ".join(category.replace("_", " ") for category in visual_categories) or "visual"
    )
    pacing_text = (
        ", ".join(category.replace("_", " ") for category in pacing_categories) or "hook and pacing"
    )
    return (
        f"Combine {visual_text} assets with {pacing_text} assets across "
        f"{len(expected_reel_formats)} reel formats. The {requested_asset_count}-asset pack is "
        "designed as a reusable starter library: each reel can swap one scene, proof, hook, "
        "or audio choice while preserving a consistent niche identity."
    )


def _working_title(niche: str, category: str, index: int) -> str:
    readable_category = category.replace("_", " ")
    return f"{niche.title()} {readable_category} {index}"


def _purpose(niche: str, category: str, expected_reel_formats: list[str]) -> str:
    format_text = ", ".join(expected_reel_formats[:2])
    return (
        f"Reusable {category.replace('_', ' ')} for {niche} reels, especially "
        f"{format_text} formats."
    )


def _prompt(
    niche: str,
    category: str,
    kind: AssetKind,
    index: int,
    style_note: str,
) -> str:
    media_word = "video" if infer_media_type_for_asset_kind(kind) is MediaType.VIDEO else "asset"
    return (
        f"Create {media_word} {index} for a {niche} reusable asset pack: "
        f"{category.replace('_', ' ')} with clean composition, strong vertical framing, "
        f"and enough negative space for captions. {style_note}"
    ).strip()


def _rationale(category: str) -> str:
    rationales = {
        "scene_setter": "Establishes reusable context so multiple reels can open quickly.",
        "proof_visual": "Supplies clear demonstration material for value and payoff beats.",
        "detail_prop": "Adds specific visual anchors that make repeated edits feel distinct.",
        "layerable_cutout": "Supports compositing and remixing without regenerating full scenes.",
        "transition_motif": "Creates pacing variety between hooks, proof, and calls to action.",
        "hook_copy": "Gives the pack reusable openings that can be paired with many visuals.",
        "audio_bed": "Creates a consistent sound bed for a recognizable reel family.",
        "overlay_system": "Keeps text treatments consistent across future reels.",
        "caption_copy": "Speeds publishing while preserving the niche-specific voice.",
        "layout_system": "Provides repeatable composition rules for fast packaging.",
        "audio_accent": "Adds repeatable emphasis for reveals and transitions.",
        "voiceover": "Anchors the pack in a reusable persona or narration style.",
    }
    return rationales.get(category, "Adds reusable material for future reel assembly.")


def _required_traits(
    category: str,
    style_persona_constraints: Mapping[str, Any],
    *,
    output_potential: OutputPotentialScore,
) -> dict[str, Any]:
    traits: dict[str, Any] = {
        "vertical_safe": True,
        "caption_safe": True,
        "category": category,
        "output_potential": {
            "score": output_potential.total_score,
            "criteria_scores": output_potential.criteria_scores,
            "rationale": output_potential.rationale,
        },
    }
    if style_persona_constraints:
        traits["style_persona_constraints"] = dict(style_persona_constraints)
    if category in {"layerable_cutout", "detail_prop"}:
        traits["isolated_subject"] = True
    if category in {"scene_setter", "proof_visual"}:
        traits["usable_as_b_roll"] = True
    return traits


def _compatibility_metadata(
    *,
    niche: str,
    category: str,
    expected_reel_formats: list[str],
    style_persona_constraints: Mapping[str, Any],
) -> AssetCompatibilityMetadata:
    visual_style = _compatibility_values(
        style_persona_constraints,
        "visual_style",
        "style",
        default=["platform_native"],
    )
    emotion = _compatibility_values(
        style_persona_constraints,
        "emotion",
        "emotional_angles",
        default=["useful"],
    )
    pace = _compatibility_values(style_persona_constraints, "pace", default=["medium"])
    base = {
        "niche": [niche],
        "topic": [niche],
        "theme": _core_motifs(niche, {category: 1}, style_persona_constraints),
        "emotion": emotion,
        "visual_style": visual_style,
        "pace": pace,
        "format_type": _formats_for_category(category, expected_reel_formats),
        "requires_safe_area": category in {"scene_setter", "proof_visual", "layout_system"},
    }
    if category == "scene_setter":
        base["works_as_background_for"] = [
            "foreground",
            "subject_video",
            "object_image",
            "transparent_cutout_png",
            "prop_image",
        ]
        base["works_with_audio_moods"] = emotion
        base["works_with_hook_types"] = _formats_for_category(category, expected_reel_formats)
    elif category in {"detail_prop", "layerable_cutout"}:
        base["requires_transparency"] = category == "layerable_cutout"
        base["works_with_object_types"] = [category, "foreground"]
    elif category == "audio_bed":
        base["works_with_audio_moods"] = emotion
    elif category == "hook_copy":
        base["works_with_hook_types"] = _formats_for_category(category, expected_reel_formats)
    return AssetCompatibilityMetadata.model_validate(base)


def _compatibility_values(
    source: Mapping[str, Any],
    *keys: str,
    default: list[str],
) -> list[str]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str):
            return [value]
        if isinstance(value, Sequence):
            return [str(item) for item in value]
    return default


def _formats_for_category(category: str, expected_reel_formats: list[str]) -> list[str]:
    if category in {"hook_copy", "scene_setter"}:
        return expected_reel_formats[:3]
    if category in {"proof_visual", "detail_prop", "layerable_cutout"}:
        return expected_reel_formats[1:] or expected_reel_formats
    return expected_reel_formats


def _style_note(style_persona_constraints: Mapping[str, Any]) -> str:
    if not style_persona_constraints:
        return "Use a flexible, platform-native visual style."
    compact = ", ".join(
        f"{key}: {value}" for key, value in sorted(style_persona_constraints.items())[:4]
    )
    return f"Respect style/persona constraints: {compact}."


def _normalize_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = " ".join(str(value).strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


__all__ = [
    "ASSET_CATEGORY_DEFAULT_KIND",
    "ASSET_KIND_CATEGORY",
    "AssetPackPlan",
    "AssetPackPlanInput",
    "AssetPackPlannedSpec",
    "DEFAULT_ASSET_WEIGHTS",
    "DEFAULT_REEL_FORMATS",
    "generate_asset_pack_plan",
    "validate_requested_asset_mix",
]
