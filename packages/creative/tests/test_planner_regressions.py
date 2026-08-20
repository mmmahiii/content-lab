from __future__ import annotations

from content_lab_creative.single_prompt_reel_planner import (
    SinglePromptPlannerInput,
    build_master_planning_prompt,
)


def _planner_input() -> SinglePromptPlannerInput:
    return SinglePromptPlannerInput(
        page_context={
            "page_id": "page_1",
            "platform": "instagram",
            "display_name": "Generic Demo",
            "asset_pack_niche": "generic product education",
        },
        selected_assets=[
            {
                "asset_id": "surface",
                "asset_label": "Studio surface",
                "asset_kind": "background_image",
                "media_type": "image",
                "possible_cinematic_roles": ["environment_base"],
                "compatibility": {
                    "view_angle": "top_down",
                    "surface_plane": "horizontal",
                    "can_be_full_frame_base": True,
                },
            },
            {
                "asset_id": "hero",
                "asset_label": "Hero object",
                "asset_kind": "transparent_cutout_png",
                "media_type": "image",
                "transparent": True,
                "possible_cinematic_roles": ["hero_subject"],
                "compatibility": {
                    "view_angle": "top_down",
                    "surface_plane": "horizontal",
                    "can_be_supported_by_surface": True,
                },
            },
        ],
        content_goal="Create one clear asset-led reel.",
        duration_target_seconds=6.0,
    )


def test_master_prompt_protects_against_asset_collage_regressions() -> None:
    prompt = build_master_planning_prompt(_planner_input()).master_prompt

    assert "Physical relationship rule" in prompt
    assert "Render strategy rule" in prompt
    assert "Static-asset motion rule" in prompt
    assert "Duplicate-role rule" in prompt
    assert "Background reveal placement rule" in prompt
    assert "z <= 0.45" in prompt
    assert "provenance.rejected_assets" in prompt


def test_planner_payload_keeps_asset_compatibility_metadata() -> None:
    package = build_master_planning_prompt(_planner_input())

    assert "view_angle" in package.master_prompt
    assert "surface_plane" in package.master_prompt
    assert "support_object_id" in package.master_prompt
