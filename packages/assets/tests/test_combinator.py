from __future__ import annotations

from content_lab_assets.combinator import (
    AssetCompatibilityMetadata,
    PackAsset,
    estimate_output_potential,
    generate_candidate_compositions,
    select_performance_weighted_combinations,
)
from content_lab_assets.types import AssetKind


def _asset(
    asset_id: str,
    asset_kind: AssetKind,
    *,
    role: str,
    performance_score: float | None = None,
    usage_count: int = 0,
    **compatibility: object,
) -> PackAsset:
    return PackAsset(
        asset_id=asset_id,
        asset_kind=asset_kind,
        pack_role=role,
        compatibility=AssetCompatibilityMetadata.model_validate(compatibility),
        performance_score=performance_score,
        usage_count=usage_count,
    )


def test_combinator_filters_incompatible_asset_pairs() -> None:
    background = _asset(
        "bg-1",
        AssetKind.BACKGROUND_VIDEO,
        role="background",
        niche=["pilates"],
        visual_style=["clean"],
        format_type=["hook_led_tip"],
        works_as_background_for=["transparent_cutout_png"],
    )
    cutout = _asset(
        "obj-1",
        AssetKind.TRANSPARENT_CUTOUT_PNG,
        role="object",
        niche=["pilates"],
        visual_style=["clean"],
        format_type=["hook_led_tip"],
        requires_transparency=True,
    )
    bad_object = _asset(
        "obj-2",
        AssetKind.OBJECT_IMAGE,
        role="object",
        niche=["finance"],
        visual_style=["dark"],
        format_type=["case_study"],
        requires_transparency=True,
    )
    hook = _asset(
        "hook-1",
        AssetKind.HOOK_TEXT,
        role="hook",
        niche=["pilates"],
        visual_style=["clean"],
        format_type=["hook_led_tip"],
        theme=["hook_led_tip"],
    )

    candidates = generate_candidate_compositions(
        [background, cutout, bad_object, hook],
        target_reel_count=5,
        format_filters=["hook-led tip"],
        style_filters=["clean"],
    )

    assert len(candidates) == 1
    assert candidates[0].roles["foreground"].asset_id == "obj-1"
    assert candidates[0].roles["hook"].asset_id == "hook-1"


def test_output_potential_reports_bottlenecks_and_suggestions() -> None:
    estimate = estimate_output_potential(
        [
            _asset("bg-1", AssetKind.BACKGROUND_VIDEO, role="background", niche=["travel"]),
            _asset("hook-1", AssetKind.HOOK_TEXT, role="hook", niche=["travel"]),
        ],
        target_reel_count=4,
    )

    assert estimate.valid_combination_count >= 1
    assert "no_audio" in estimate.bottlenecks
    assert "Add audio tracks with explicit moods." in estimate.suggested_assets


def test_performance_weighted_selection_cools_down_overused_winners() -> None:
    assets = [
        _asset(
            "bg-winner",
            AssetKind.BACKGROUND_VIDEO,
            role="background",
            niche=["fitness"],
            performance_score=0.98,
            usage_count=2,
        ),
        _asset(
            "bg-fresh",
            AssetKind.BACKGROUND_VIDEO,
            role="background",
            niche=["fitness"],
            performance_score=0.72,
            usage_count=0,
        ),
        _asset(
            "hook-1",
            AssetKind.HOOK_TEXT,
            role="hook",
            niche=["fitness"],
            performance_score=0.8,
        ),
    ]

    exploit = select_performance_weighted_combinations(
        assets,
        target_reel_count=1,
        mode="exploit",
    )
    explore = select_performance_weighted_combinations(
        assets,
        target_reel_count=1,
        mode="explore",
    )

    assert exploit[0].roles["background"].asset_id == "bg-winner"
    assert explore[0].roles["background"].asset_id == "bg-fresh"
