from __future__ import annotations

import pytest

from content_lab_assets.planner import generate_asset_pack_plan


def test_generate_asset_pack_plan_defaults_mix_and_matches_requested_count() -> None:
    plan = generate_asset_pack_plan(
        niche="pilates for beginners",
        requested_asset_count=8,
    )

    assert sum(plan.asset_mix.values()) == 8
    assert len(plan.planned_asset_specs) == 8
    assert plan.planned_asset_specs[0].compatibility.niche == ["pilates_for_beginners"]
    assert plan.planned_asset_specs[0].compatibility.format_type
    assert plan.asset_pack_plan["asset_mix_source"] == "default"
    assert plan.expected_reel_formats
    assert "future reels" in plan.reuse_rationale
    assert all(spec.purpose for spec in plan.planned_asset_specs)
    assert "output_potential_scoring" in plan.asset_pack_plan
    assert all(spec.output_potential_score > 0 for spec in plan.planned_asset_specs)


def test_generate_asset_pack_plan_uses_requested_mix_and_reel_formats() -> None:
    plan = generate_asset_pack_plan(
        niche="coffee shop marketing",
        requested_asset_count=3,
        asset_mix={"background_video": 2, "transparent_cutout_png": 1},
        target_reel_types=["menu reveal", "founder tip"],
        style_persona_constraints={"tone": "warm", "palette": "high contrast"},
    )

    assert plan.asset_mix == {"background_video": 2, "transparent_cutout_png": 1}
    assert len(plan.planned_asset_specs) == 3
    assert set(plan.asset_mix) == {"background_video", "transparent_cutout_png"}
    assert plan.asset_pack_plan["asset_mix_source"] == "requested"
    assert plan.expected_reel_formats == ["menu reveal", "founder tip"]
    assert all(
        spec.compatible_with["style_persona_constraints"]["tone"] == "warm"
        for spec in plan.planned_asset_specs
    )


def test_generate_asset_pack_plan_accepts_category_mix_keys() -> None:
    plan = generate_asset_pack_plan(
        niche="luxury mindset",
        requested_asset_count=6,
        asset_mix={
            "scene_setter": 2,
            "detail_prop": 2,
            "hooks": 1,
            "audio_moods": 1,
        },
    )

    assert plan.asset_mix == {
        "background_video": 2,
        "prop_image": 2,
        "hook_text": 1,
        "audio_track": 1,
    }
    assert len(plan.planned_asset_specs) == 6


def test_generate_asset_pack_plan_rejects_requested_mix_total_mismatch() -> None:
    with pytest.raises(ValueError, match="asset_mix total must equal requested_asset_count"):
        generate_asset_pack_plan(
            niche="coffee shop marketing",
            requested_asset_count=5,
            asset_mix={"background_video": 2, "transparent_cutout_png": 1},
        )


def test_generate_asset_pack_plan_rejects_empty_mix() -> None:
    with pytest.raises(ValueError, match="at least one positive count"):
        generate_asset_pack_plan(
            niche="travel",
            requested_asset_count=3,
            asset_mix={"background_video": 0},
        )


def test_generate_asset_pack_plan_returns_guidance_for_narrow_mix() -> None:
    plan = generate_asset_pack_plan(
        niche="travel",
        requested_asset_count=10,
        asset_mix={"background_video": 10},
    )

    assert plan.asset_mix == {"background_video": 10}
    assert plan.asset_pack_plan["asset_mix_guidance"]


def test_generate_asset_pack_plan_scores_and_prioritizes_output_potential() -> None:
    plan = generate_asset_pack_plan(
        niche="luxury mindset",
        requested_asset_count=8,
        asset_mix={
            "caption_text": 2,
            "background_video": 2,
            "transparent_cutout_png": 2,
            "audio_track": 1,
            "hook_text": 1,
        },
        target_reel_types=["belief shift", "daily ritual", "before-after"],
        style_persona_constraints={"tone": "cinematic mentor"},
    )

    scores_by_priority = [spec.output_potential_score for spec in plan.planned_asset_specs]
    assert scores_by_priority == sorted(scores_by_priority, reverse=True)
    assert [spec.priority for spec in plan.planned_asset_specs] == list(range(8))
    assert plan.planned_asset_specs[0].category in {"scene_setter", "layerable_cutout"}
    assert plan.planned_asset_specs[-1].category == "caption_copy"

    first_spec = plan.planned_asset_specs[0]
    assert set(first_spec.output_potential_scores) == {
        "reuse_potential",
        "combination_potential",
        "visual_flexibility",
        "niche_relevance",
        "realism_support",
        "format_coverage",
        "cost_saving_potential",
        "novelty_without_bloat",
    }
    assert first_spec.output_potential_rationale
    assert (
        first_spec.required_traits["output_potential"]["score"] == first_spec.output_potential_score
    )
    assert (
        plan.asset_pack_plan["output_potential_scoring"]["priority_method"]
        == "weighted_output_potential_desc"
    )


def test_generate_asset_pack_plan_builds_human_readable_strategy_summary() -> None:
    plan = generate_asset_pack_plan(
        niche="luxury mindset",
        target_audience="early-stage founders",
        requested_asset_count=6,
        asset_mix={
            "background_video": 2,
            "prop_image": 1,
            "hook_text": 2,
            "audio_track": 1,
        },
        target_reel_types=["belief shift", "daily ritual"],
        style_persona_constraints={
            "visual_style": "cinematic minimalism",
            "emotional_angles": ["aspiration without noise", "quiet confidence"],
            "core_motifs": ["morning desk ritual", "premium notebook"],
        },
    )

    strategy = plan.asset_pack_plan["pack_strategy"]
    assert strategy["niche"] == "luxury mindset"
    assert strategy["target_audience"] == "early-stage founders"
    assert strategy["visual_style"] == "visual_style: cinematic minimalism"
    assert strategy["emotional_angles"] == ["aspiration without noise", "quiet confidence"]
    assert strategy["core_motifs"] == ["morning desk ritual", "premium notebook"]
    assert strategy["asset_category_split"] == {
        "audio_bed": 1,
        "detail_prop": 1,
        "hook_copy": 2,
        "scene_setter": 2,
    }
    assert strategy["expected_reel_formats"] == ["belief shift", "daily ritual"]
    assert strategy["why_these_assets_were_chosen"]
    assert "Multi-reel plan" in plan.strategy_summary
    assert "early-stage founders" in plan.strategy_summary
    assert "random" not in plan.strategy_summary.lower()


def test_generate_asset_pack_plan_discounts_duplicate_category_bloat() -> None:
    plan = generate_asset_pack_plan(
        niche="travel",
        requested_asset_count=5,
        asset_mix={"background_video": 5},
    )

    novelty_scores = [
        spec.output_potential_scores["novelty_without_bloat"] for spec in plan.planned_asset_specs
    ]
    assert novelty_scores == sorted(novelty_scores, reverse=True)
    assert novelty_scores[0] > novelty_scores[-1]
    assert "avoid filler" in " ".join(plan.planned_asset_specs[-1].output_potential_rationale)
