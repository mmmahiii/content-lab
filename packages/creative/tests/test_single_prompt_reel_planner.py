from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from content_lab_creative.planning_schema import CinematicReelPlan
from content_lab_creative.scene_regulator import regulate_cinematic_plan
from content_lab_creative.single_prompt_reel_planner import (
    ARTIFACT_FILENAMES,
    PLANNING_PROMPT_VERSION,
    SinglePromptPlannerInput,
    build_master_planning_prompt,
    compute_plan_hash,
    validate_pasted_cinematic_plan,
)


def _planner_input() -> SinglePromptPlannerInput:
    return SinglePromptPlannerInput(
        page_context={
            "display_name": "Kitchen Lab",
            "platform": "instagram",
            "niche": "steak cooking",
        },
        selected_assets=[
            {
                "asset_id": "kitchen_bg",
                "asset_label": "Kitchen background",
                "asset_kind": "background_video",
                "media_type": "video",
                "possible_cinematic_roles": ["environment_base"],
            },
            {
                "asset_id": "steak_clip",
                "asset_label": "Steak closeup",
                "asset_kind": "subject_video",
                "media_type": "video",
                "possible_cinematic_roles": ["hero_subject"],
            },
            {
                "asset_id": "steam_overlay",
                "asset_label": "Steam overlay",
                "asset_kind": "effect_video",
                "media_type": "video",
                "possible_cinematic_roles": ["atmospheric_layer"],
            },
            {
                "asset_id": "sizzle_audio",
                "asset_label": "Oil sizzle",
                "asset_kind": "sound_effect",
                "media_type": "audio",
                "possible_cinematic_roles": ["audio_layer"],
            },
            {
                "asset_id": "herb_pot",
                "asset_label": "Herb pot",
                "asset_kind": "prop_image",
                "media_type": "image",
                "possible_cinematic_roles": ["supporting_subject"],
            },
        ],
        content_goal="Make steak prep feel cinematic and appetising.",
        platform_constraints={"platform": "instagram", "aspect_ratio": "9:16"},
        duration_target_seconds=6.5,
        pinned_prompt_paths=["sensory_hook"],
    )


def _motion() -> dict[str, object]:
    return {
        "type": "linear",
        "start_value": {"x": 0.5, "y": 0.5, "scale": 1.0},
        "end_value": {"x": 0.5, "y": 0.48, "scale": 1.04},
        "easing": "ease_in_out",
        "jitter_allowed": False,
        "speed": 0.2,
        "sync_to_audio": None,
    }


def _shadow(enabled: bool, *, contact: bool = False, opacity: float = 0.3) -> dict[str, object]:
    return {
        "enabled": enabled,
        "source_light_id": "key_window" if enabled else None,
        "offset_x": 0.03 if enabled else 0.0,
        "offset_y": 0.05 if enabled else 0.0,
        "blur": 0.22 if contact else 0.55,
        "opacity": opacity if enabled else 0.0,
        "softness": 0.55 if contact else 0.9,
        "derived_from_z_depth": True,
        "contact_shadow_required": contact,
    }


def _blur() -> dict[str, float]:
    return {"radius": 0.0, "background_blur": 0.0, "motion_blur": 0.04}


def _object(
    object_id: str,
    asset_id: str,
    asset_label: str,
    role: str,
    scene_id: str,
    start: float,
    end: float,
    *,
    z: float,
    width: float,
    height: float,
    scale: float,
    shadow: dict[str, object],
) -> dict[str, object]:
    return {
        "object_id": object_id,
        "asset_id": asset_id,
        "asset_label": asset_label,
        "role": role,
        "scene_id": scene_id,
        "start_time": start,
        "end_time": end,
        "x": 0.5,
        "y": 0.52,
        "z": z,
        "scale": scale,
        "width_normalised": width,
        "height_normalised": height,
        "rotation": 0.0,
        "opacity": 1.0,
        "anchor_point": "center",
        "motion_curve": _motion(),
        "shadow_spec": shadow,
        "blur_spec": _blur(),
        "occlusion_group": f"{scene_id}_table",
        "realism_reason": f"{asset_label} has a clear role in the filmed kitchen moment.",
    }


def _caption(caption_id: str, text: str, role: str, start: float, end: float) -> dict[str, object]:
    return {
        "caption_id": caption_id,
        "text": text,
        "role": role,
        "start_time": start,
        "end_time": end,
        "x": 0.5,
        "y": 0.14,
        "max_width": 0.72,
        "font_size": 54,
        "weight": "bold",
        "alignment": "center",
        "animation": "fade_up",
        "safe_area": {"top": 0.08, "right": 0.06, "bottom": 0.08, "left": 0.06},
        "safe_area_compliant": True,
        "renderer_text_only": True,
    }


def valid_plan_dict(planner_input: SinglePromptPlannerInput | None = None) -> dict[str, object]:
    planner_input = planner_input or _planner_input()
    camera_1 = {
        "move_type": "slow_push_in",
        "start_time": 0.0,
        "end_time": 3.0,
        "crop_x": 0.5,
        "crop_y": 0.5,
        "zoom": 1.04,
        "rotation": 0.0,
        "shake_intensity": 0.02,
        "shake_frequency": 6.0,
        "motion_curve": _motion(),
    }
    camera_2 = {**camera_1, "start_time": 3.0, "end_time": 6.5, "zoom": 1.08}
    audio_layer = {
        "audio_id": "audio_sizzle",
        "asset_id": "sizzle_audio",
        "role": "sensory_sizzle",
        "start_time": 0.0,
        "end_time": 6.5,
        "volume": 0.85,
        "fade_in": 0.0,
        "fade_out": 0.4,
        "sync_points": [{"time": 0.2, "label": "first_sizzle", "target_object_id": "steak_hero_1"}],
    }
    scenes = [
        {
            "scene_id": "scene_1",
            "start_time": 0.0,
            "end_time": 3.0,
            "purpose": "Open on a tactile steak sizzle with the kitchen as one coherent set.",
            "dominant_focal_role": "hero_subject",
            "emotional_intent": "Immediate appetite and sensory attention.",
            "visual_density": "medium",
            "camera_move": camera_1,
            "objects": [
                _object(
                    "kitchen_bg_1",
                    "kitchen_bg",
                    "Kitchen background",
                    "environment_base",
                    "scene_1",
                    0.0,
                    3.0,
                    z=0.05,
                    width=1.0,
                    height=1.0,
                    scale=1.0,
                    shadow=_shadow(False),
                ),
                _object(
                    "steak_hero_1",
                    "steak_clip",
                    "Steak closeup",
                    "hero_subject",
                    "scene_1",
                    0.0,
                    3.0,
                    z=0.72,
                    width=0.62,
                    height=0.42,
                    scale=0.95,
                    shadow=_shadow(True, contact=True, opacity=0.45),
                ),
                _object(
                    "steam_1",
                    "steam_overlay",
                    "Steam overlay",
                    "atmospheric_layer",
                    "scene_1",
                    0.4,
                    3.0,
                    z=0.86,
                    width=0.9,
                    height=0.5,
                    scale=1.0,
                    shadow=_shadow(False),
                ),
            ],
            "captions": [_caption("cap_hook", "That first sizzle matters", "hook", 0.4, 1.8)],
            "audio_layers": [],
            "transition_in": None,
            "transition_out": "steam_match_cut",
        },
        {
            "scene_id": "scene_2",
            "start_time": 3.0,
            "end_time": 6.5,
            "purpose": "Pay off the closeup by holding on the finished steak texture.",
            "dominant_focal_role": "hero_subject",
            "emotional_intent": "Premium calm and satisfying finish.",
            "visual_density": "low",
            "camera_move": camera_2,
            "objects": [
                _object(
                    "kitchen_bg_2",
                    "kitchen_bg",
                    "Kitchen background",
                    "environment_base",
                    "scene_2",
                    3.0,
                    6.5,
                    z=0.05,
                    width=1.0,
                    height=1.0,
                    scale=1.0,
                    shadow=_shadow(False),
                ),
                _object(
                    "steak_hero_2",
                    "steak_clip",
                    "Steak closeup",
                    "hero_subject",
                    "scene_2",
                    3.0,
                    6.5,
                    z=0.74,
                    width=0.68,
                    height=0.46,
                    scale=1.0,
                    shadow=_shadow(True, contact=True, opacity=0.42),
                ),
            ],
            "captions": [_caption("cap_payoff", "Pull it when it shines", "payoff", 4.7, 6.1)],
            "audio_layers": [],
            "transition_in": "steam_match_cut",
            "transition_out": "loop_to_sizzle",
        },
    ]
    object_shadows = [
        {"object_id": item["object_id"], **item["shadow_spec"]}
        for scene in scenes
        for item in scene["objects"]
    ]
    return {
        "plan_id": "plan_kitchen_sizzle",
        "page_context_summary": "Kitchen Lab makes short, sensory steak cooking reels.",
        "content_goal": "Make steak prep feel cinematic and appetising.",
        "selected_prompt_paths": ["sensory_hook", "satisfying_process", "cinematic_closeup"],
        "narrative_arc": {
            "hook": "The sizzle catches attention before copy appears.",
            "development": "Steam and camera push make the steak feel tactile.",
            "reveal_payoff": "The hero closeup resolves as a finished appetising texture.",
            "closing_retention_loop": "The final glisten can loop back into the opening sizzle.",
        },
        "total_duration_seconds": 6.5,
        "fps": 24,
        "canvas": {"aspect_ratio": "9:16", "width": 1080, "height": 1920},
        "scenes": scenes,
        "global_camera_style": "Controlled closeup push with tiny handheld motion.",
        "global_lighting_style": "Warm window light from upper left with soft food shadows.",
        "caption_strategy": "Two short editable captions that avoid the steak.",
        "audio_strategy": "Use selected sizzle audio as the sensory anchor.",
        "lighting_shadow_plan": {
            "lights": [
                {
                    "light_id": "key_window",
                    "type": "window",
                    "x": 0.2,
                    "y": 0.12,
                    "z": 0.9,
                    "intensity": 1.2,
                    "colour_temperature": 4300,
                    "softness": 0.75,
                }
            ],
            "per_object_shadow_specs": object_shadows,
            "global_colour_temperature": 4300,
            "contrast_level": "medium",
        },
        "audio_plan": {
            "layers": [audio_layer],
            "sync_points": [{"time": 0.2, "label": "first_sizzle", "target_object_id": "steak_hero_1"}],
            "sensory_moments": ["0.2s first sizzle", "4.8s payoff glisten"],
        },
        "realism_constraints": {
            "dominant_subject_required": True,
            "max_foreground_objects": 3,
            "require_contact_shadows": True,
            "forbid_floating_assets": True,
            "forbid_baked_text": True,
            "forbid_fake_ui": True,
            "require_depth_consistency": True,
            "require_caption_safe_area": True,
            "require_motion_continuity": True,
        },
        "render_notes": ["Use stored registry assets only; captions remain editable renderer text."],
        "provenance": {
            "input_page_context_hash": planner_input.input_page_context_hash,
            "selected_asset_ids": planner_input.selected_asset_ids,
            "selected_prompt_paths": ["sensory_hook", "satisfying_process", "cinematic_closeup"],
            "planning_prompt_version": PLANNING_PROMPT_VERSION,
            "plan_hash": "",
            "rejected_assets": [
                {
                    "asset_id": "herb_pot",
                    "reason": "The herb pot would add clutter and has no narrative purpose.",
                }
            ],
            "realism_risk_score": 0.2,
        },
    }


def test_master_prompt_uses_page_context_and_assets_without_screenshot_input() -> None:
    package = build_master_planning_prompt(_planner_input())

    assert package.recommended_model == "gpt-5-mini"
    assert package.selected_asset_ids == [
        "kitchen_bg",
        "steak_clip",
        "steam_overlay",
        "sizzle_audio",
        "herb_pot",
    ]
    assert "Do not request screenshots" in package.master_prompt
    assert "selected_assets" in package.master_prompt
    assert "CinematicReelPlan" in package.master_prompt
    assert "Do not invent asset-specific roles" in package.master_prompt
    assert "hero_subject" in package.master_prompt
    assert "slow_push_in" in package.master_prompt
    assert "ambient_room" in package.master_prompt


def test_prompt_paths_are_stackable_and_context_sensitive() -> None:
    food_paths = _planner_input().suggested_prompt_paths
    business_paths = SinglePromptPlannerInput(
        page_context={"niche": "B2B SaaS operations"},
        selected_assets=[
            {
                "asset_id": "dashboard_video",
                "asset_label": "Dashboard motion",
                "asset_kind": "source_clip",
                "media_type": "video",
            }
        ],
        content_goal="Show the founder problem and product result.",
        banned_prompt_paths=["sensory_hook"],
    ).suggested_prompt_paths

    assert food_paths[:3] == ["sensory_hook", "satisfying_process", "cinematic_closeup"]
    assert "problem_solution" in business_paths
    assert "sensory_hook" not in business_paths


def test_valid_plan_accepts_unused_rejected_asset_and_splits_artifacts() -> None:
    validated = validate_pasted_cinematic_plan(
        json.dumps(valid_plan_dict()),
        planner_input=_planner_input(),
    )

    assert validated.plan.provenance.rejected_assets[0].asset_id == "herb_pot"
    assert validated.validation_report["passed"] is True
    assert set(validated.artifacts) == set(ARTIFACT_FILENAMES)
    assert validated.artifacts["caption_plan.json"]["captions"][0]["renderer_text_only"] is True
    assert validated.artifacts["reel_timeline.json"]["objects"][0]["z"] == 0.05
    assert validated.artifacts["provenance.json"]["plan_hash"] == validated.plan_hash


def test_pasted_plan_alias_drift_is_normalized_before_validation() -> None:
    payload = valid_plan_dict()
    scene_1 = payload["scenes"][0]  # type: ignore[index]
    scene_2 = payload["scenes"][1]  # type: ignore[index]
    scene_1["dominant_focal_role"] = "hero_tomato"
    scene_1["camera_move"]["move_type"] = "push_in"
    scene_1["objects"][1]["role"] = "hero_tomato_loop"
    scene_1["objects"][2]["height_normalised"] = 1.2
    scene_1["audio_layers"] = [
        {
            "audio_id": "audio_music_bed",
            "asset_id": "sizzle_audio",
            "role": "music_bed",
            "start_time": 0.0,
            "end_time": 3.0,
            "volume": 0.45,
            "fade_in": 0.1,
            "fade_out": 0.2,
            "sync_points": [],
        }
    ]
    scene_2["camera_move"]["move_type"] = "micro_pullback"
    scene_2["objects"][1]["role"] = "ingredient_step"
    payload["audio_plan"]["layers"][0]["role"] = "foley_accents"  # type: ignore[index]

    validated = validate_pasted_cinematic_plan(payload, planner_input=_planner_input())

    repairs = validated.validation_report["normalization"]["repairs"]
    repair_paths = {item["path"] for item in repairs}
    assert validated.validation_report["normalization"]["applied"] is True
    assert validated.plan.scenes[0].dominant_focal_role == "hero_subject"
    assert validated.plan.scenes[0].camera_move.move_type == "slow_push_in"
    assert validated.plan.scenes[0].objects[2].height_normalised == 1.0
    assert validated.plan.scenes[0].audio_layers[0].role == "ambient_room"
    assert validated.plan.scenes[1].camera_move.move_type == "slow_pull_out"
    assert validated.plan.audio_plan.layers[0].role == "impact"
    assert "scenes.0.dominant_focal_role" in repair_paths
    assert "scenes.0.camera_move.move_type" in repair_paths
    assert "scenes.0.objects.2.height_normalised" in repair_paths
    assert "audio_plan.layers.0.role" in repair_paths


def test_every_scene_has_dominant_focal_role_and_timeline_coordinates() -> None:
    plan = CinematicReelPlan.model_validate(valid_plan_dict())

    for scene in plan.scenes:
        assert any(item.role == scene.dominant_focal_role for item in scene.objects)
        for item in scene.objects:
            assert 0.0 <= item.x <= 1.0
            assert 0.0 <= item.y <= 1.0
            assert 0.0 <= item.z <= 1.0
            assert item.scale > 0
            assert item.start_time < item.end_time
            assert item.realism_reason


def test_captions_are_safe_renderer_text_only() -> None:
    plan = CinematicReelPlan.model_validate(valid_plan_dict())

    captions = [caption for scene in plan.scenes for caption in scene.captions]
    assert captions
    assert all(caption.safe_area_compliant and caption.renderer_text_only for caption in captions)
    assert all(caption.safe_area.top <= caption.y <= 1.0 - caption.safe_area.bottom for caption in captions)


def test_deterministic_plan_hash_is_stable_for_fixed_inputs() -> None:
    validated_a = validate_pasted_cinematic_plan(valid_plan_dict(), planner_input=_planner_input())
    validated_b = validate_pasted_cinematic_plan(valid_plan_dict(), planner_input=_planner_input())

    assert validated_a.plan_hash == validated_b.plan_hash
    assert compute_plan_hash(validated_a.plan) == validated_a.plan_hash


def test_references_outside_selected_assets_are_rejected() -> None:
    payload = valid_plan_dict()
    payload["scenes"][0]["objects"][1]["asset_id"] = "hallucinated_asset"  # type: ignore[index]

    with pytest.raises((ValidationError, ValueError), match="unselected assets"):
        validate_pasted_cinematic_plan(payload, planner_input=_planner_input())


def test_external_generation_instructions_are_rejected() -> None:
    payload = valid_plan_dict()
    payload["render_notes"] = ["call runway to create video for the final beat"]

    with pytest.raises((ValidationError, ValueError), match="external generation|forbidden"):
        validate_pasted_cinematic_plan(payload, planner_input=_planner_input())


def test_floating_asset_collage_fails_scene_regulation() -> None:
    payload = valid_plan_dict()
    scene = payload["scenes"][0]  # type: ignore[index]
    extra_a = copy.deepcopy(scene["objects"][1])
    extra_a["object_id"] = "steak_hero_extra_a"
    extra_a["x"] = 0.3
    extra_b = copy.deepcopy(scene["objects"][1])
    extra_b["object_id"] = "steak_hero_extra_b"
    extra_b["x"] = 0.7
    scene["objects"].extend([extra_a, extra_b])
    payload["lighting_shadow_plan"]["per_object_shadow_specs"].extend(  # type: ignore[index]
        [
            {"object_id": extra_a["object_id"], **extra_a["shadow_spec"]},
            {"object_id": extra_b["object_id"], **extra_b["shadow_spec"]},
        ]
    )
    plan = CinematicReelPlan.model_validate(payload)

    report = regulate_cinematic_plan(plan)

    assert not report.passed
    assert "too_many_high_priority_objects" in report.as_dict()["failure_codes"]


def test_missing_dominant_subject_fails_validation() -> None:
    payload = valid_plan_dict()
    payload["scenes"][0]["dominant_focal_role"] = "brand_marker"  # type: ignore[index]

    with pytest.raises(ValidationError, match="dominant_focal_role"):
        CinematicReelPlan.model_validate(payload)
