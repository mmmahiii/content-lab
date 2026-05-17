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
    normalize_pasted_plan_payload,
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
    assert "CRITICAL MANUAL-MODE RULE" in package.master_prompt
    assert "Use the minimum number of selected assets" in package.master_prompt
    assert "no more than 3 visible foreground objects" in package.master_prompt
    assert "Every scene must begin with an environment_base object" in package.master_prompt
    assert "Before returning, silently check" in package.master_prompt
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


def test_validation_repairs_provenance_selected_assets_from_planner_input() -> None:
    payload = valid_plan_dict()
    provenance = payload["provenance"]  # type: ignore[index]
    provenance["selected_asset_ids"] = ["kitchen_bg", "steak_clip"]  # type: ignore[index]
    provenance["rejected_assets"] = []  # type: ignore[index]

    validated = validate_pasted_cinematic_plan(payload, planner_input=_planner_input())

    assert validated.plan.provenance.selected_asset_ids == _planner_input().selected_asset_ids
    assert {item.asset_id for item in validated.plan.provenance.rejected_assets} == {"herb_pot"}
    repairs = validated.validation_report["normalization"]["repairs"]
    assert any(item["path"] == "provenance.selected_asset_ids" for item in repairs)
    assert any(item["path"] == "provenance.rejected_assets" for item in repairs)


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


def test_reported_cinematic_plan_drift_values_are_normalized() -> None:
    payload = {
        "scenes": [
            {
                "dominant_focal_role": "eggplant tactile hook",
                "camera_move": {"move_type": "push_in"},
                "objects": [
                    {"role": "environment_base", "height_normalised": 1.2},
                    {"role": "dominant_subject"},
                ],
                "audio_layers": [{"role": "scene slide accent"}],
            },
            {
                "dominant_focal_role": "mise-en-place ingredient build",
                "camera_move": {"move_type": "slide_right"},
                "objects": [
                    {"role": "environment_base", "height_normalised": 1.18},
                    {"role": "supporting_subject"},
                    {"role": "foreground_texture"},
                    {"role": "colour_contrast_subject"},
                ],
                "audio_layers": [{"role": "tomato and pepper placement accents"}],
            },
            {
                "dominant_focal_role": "finished topping reveal",
                "camera_move": {"move_type": "pull_back"},
                "objects": [
                    {"role": "environment_base", "height_normalised": 1.14},
                    {"role": "payoff_prop"},
                    {"role": "fresh_finish_subject"},
                    {"role": "texture_accent"},
                ],
                "audio_layers": [{"role": "payoff reveal lift"}],
            },
            {
                "dominant_focal_role": "final composed prep frame",
                "camera_move": {"move_type": "locked_off"},
                "objects": [
                    {"role": "environment_base", "height_normalised": 1.14},
                    {"role": "loop_anchor_ingredient"},
                    {"role": "final_payoff_prop"},
                    {"role": "fresh_loop_detail"},
                ],
                "audio_layers": [{"role": "final ambience hold"}],
            },
        ],
        "audio_plan": {
            "layers": [
                {"role": "ambient kitchen bed"},
                {"role": "diegetic food movement accents"},
                {"role": "payoff lift"},
            ]
        },
    }

    normalized, repairs = normalize_pasted_plan_payload(payload)

    assert [scene["camera_move"]["move_type"] for scene in normalized["scenes"]] == [
        "slow_push_in",
        "slight_pan_right",
        "slow_pull_out",
        "static_lockoff",
    ]
    assert [scene["dominant_focal_role"] for scene in normalized["scenes"]] == [
        "hero_subject",
        "supporting_subject",
        "narrative_payoff",
        "narrative_payoff",
    ]
    assert normalized["scenes"][0]["objects"][0]["height_normalised"] == 1.0
    assert normalized["scenes"][1]["objects"][3]["role"] == "supporting_subject"
    assert normalized["scenes"][2]["objects"][1]["role"] == "narrative_payoff"
    assert normalized["scenes"][2]["objects"][3]["role"] == "foreground_texture"
    assert normalized["scenes"][3]["objects"][1]["role"] == "supporting_subject"
    assert normalized["scenes"][3]["objects"][3]["role"] == "foreground_texture"
    assert [scene["audio_layers"][0]["role"] for scene in normalized["scenes"]] == [
        "impact",
        "impact",
        "subtle_riser",
        "ambient_room",
    ]
    assert [layer["role"] for layer in normalized["audio_plan"]["layers"]] == [
        "ambient_room",
        "impact",
        "subtle_riser",
    ]
    assert repairs


def test_reported_ingredient_plan_drift_values_are_normalized() -> None:
    payload = {
        "scenes": [
            {
                "dominant_focal_role": "hero_tomato_slice",
                "camera_move": {"move_type": "push_in"},
                "objects": [{"role": "environment_base"}, {"role": "hero_ingredient"}],
            },
            {
                "dominant_focal_role": "support_eggplant_cut",
                "camera_move": {"move_type": "lateral_slide"},
                "objects": [
                    {"role": "environment_base"},
                    {"role": "supporting_ingredient"},
                    {"role": "dominant_prep_ingredient"},
                    {"role": "colour_contrast_ingredient"},
                ],
            },
            {
                "dominant_focal_role": "payoff_basil_garnish",
                "camera_move": {"move_type": "slow_pull_out"},
                "objects": [
                    {"role": "environment_base"},
                    {"role": "supporting_prep_base"},
                    {"role": "supporting_colour_base"},
                    {"role": "payoff_garnish"},
                ],
            },
            {
                "dominant_focal_role": "completed_prep_composition",
                "camera_move": {"move_type": "locked_off"},
                "objects": [
                    {"role": "environment_base"},
                    {"role": "loop_bridge_ingredient"},
                    {"role": "fresh_finish_detail"},
                ],
            },
        ],
        "audio_plan": {
            "layers": [
                {"role": "music_bed"},
                {"role": "foley_accents"},
            ]
        },
    }

    normalized, repairs = normalize_pasted_plan_payload(payload)

    assert [scene["dominant_focal_role"] for scene in normalized["scenes"]] == [
        "hero_subject",
        "supporting_subject",
        "narrative_payoff",
        "supporting_subject",
    ]
    assert [scene["camera_move"]["move_type"] for scene in normalized["scenes"]] == [
        "slow_push_in",
        "slight_pan_right",
        "slow_pull_out",
        "static_lockoff",
    ]
    assert [item["role"] for item in normalized["scenes"][0]["objects"]] == [
        "environment_base",
        "hero_subject",
    ]
    assert [item["role"] for item in normalized["scenes"][1]["objects"]] == [
        "environment_base",
        "supporting_subject",
        "hero_subject",
        "supporting_subject",
    ]
    assert [item["role"] for item in normalized["scenes"][2]["objects"]] == [
        "environment_base",
        "supporting_subject",
        "supporting_subject",
        "narrative_payoff",
    ]
    assert [item["role"] for item in normalized["scenes"][3]["objects"]] == [
        "environment_base",
        "supporting_subject",
        "foreground_texture",
    ]
    assert [layer["role"] for layer in normalized["audio_plan"]["layers"]] == [
        "ambient_room",
        "impact",
    ]
    assert repairs


def test_reported_texture_assembly_plan_drift_values_are_normalized() -> None:
    payload = {
        "scenes": [
            {
                "dominant_focal_role": "tomato foreground texture",
                "camera_move": {"move_type": "push_in"},
                "objects": [{"role": "environment_base"}, {"role": "hero_ingredient"}],
                "audio_layers": [
                    {"role": "ambient rhythmic kitchen bed"},
                    {"role": "ingredient placement foley"},
                ],
            },
            {
                "dominant_focal_role": "vegetable layer assembly",
                "camera_move": {"move_type": "tilt_down"},
                "objects": [
                    {"role": "environment_base"},
                    {"role": "supporting_ingredient_colour"},
                    {"role": "base_ingredient_layer"},
                    {"role": "continuity_hero_ingredient"},
                ],
                "audio_layers": [
                    {"role": "ambient rhythmic kitchen bed"},
                    {"role": "ingredient placement foley"},
                ],
            },
            {
                "dominant_focal_role": "finished prep bowl and topping",
                "camera_move": {"move_type": "pull_back"},
                "objects": [
                    {"role": "environment_base"},
                    {"role": "payoff_prep_bowl"},
                    {"role": "final_texture_topping"},
                    {"role": "loop_edge_anchor"},
                ],
                "audio_layers": [
                    {"role": "ambient rhythmic kitchen bed"},
                    {"role": "ingredient placement foley"},
                ],
            },
            {
                "dominant_focal_role": "final garnish",
                "camera_move": {"move_type": "locked"},
                "objects": [
                    {"role": "environment_base"},
                    {"role": "final_prep_anchor"},
                    {"role": "final_garnish"},
                ],
                "audio_layers": [
                    {"role": "ambient rhythmic kitchen bed"},
                    {"role": "payoff accent"},
                ],
            },
        ],
        "audio_plan": {
            "layers": [
                {"role": "ambient rhythmic kitchen bed"},
                {"role": "ingredient placement foley"},
                {"role": "payoff accent"},
            ]
        },
    }

    normalized, repairs = normalize_pasted_plan_payload(payload)

    assert [scene["dominant_focal_role"] for scene in normalized["scenes"]] == [
        "hero_subject",
        "supporting_subject",
        "narrative_payoff",
        "narrative_payoff",
    ]
    assert [scene["camera_move"]["move_type"] for scene in normalized["scenes"]] == [
        "slow_push_in",
        "slight_pan_right",
        "slow_pull_out",
        "static_lockoff",
    ]
    assert [item["role"] for item in normalized["scenes"][1]["objects"]] == [
        "environment_base",
        "supporting_subject",
        "supporting_subject",
        "hero_subject",
    ]
    assert [item["role"] for item in normalized["scenes"][2]["objects"]] == [
        "environment_base",
        "narrative_payoff",
        "foreground_texture",
        "transition_element",
    ]
    assert [scene["audio_layers"][0]["role"] for scene in normalized["scenes"]] == [
        "ambient_room",
        "ambient_room",
        "ambient_room",
        "ambient_room",
    ]
    assert [scene["audio_layers"][1]["role"] for scene in normalized["scenes"]] == [
        "impact",
        "impact",
        "impact",
        "impact",
    ]
    assert [layer["role"] for layer in normalized["audio_plan"]["layers"]] == [
        "ambient_room",
        "impact",
        "impact",
    ]
    assert repairs


def test_direct_schema_validation_canonicalizes_planner_enum_drift() -> None:
    payload = valid_plan_dict()
    scene_1 = payload["scenes"][0]  # type: ignore[index]
    scene_2 = payload["scenes"][1]  # type: ignore[index]
    scene_1["dominant_focal_role"] = "tomato foreground texture"
    scene_1["camera_move"]["move_type"] = "push_in"
    scene_1["objects"][1]["role"] = "hero_ingredient"
    scene_1["audio_layers"] = [
        {
            "audio_id": "audio_scene_bed",
            "asset_id": "sizzle_audio",
            "role": "ambient rhythmic kitchen bed",
            "start_time": 0.0,
            "end_time": 3.0,
            "volume": 0.3,
            "fade_in": 0.1,
            "fade_out": 0.1,
            "sync_points": [],
        }
    ]
    scene_2["dominant_focal_role"] = "vegetable layer assembly"
    scene_2["camera_move"]["move_type"] = "tilt_down"
    scene_2["objects"][1]["role"] = "supporting_ingredient_colour"
    payload["audio_plan"]["layers"][0]["role"] = "payoff accent"  # type: ignore[index]

    plan = CinematicReelPlan.model_validate(payload)

    assert plan.scenes[0].dominant_focal_role == "hero_subject"
    assert plan.scenes[0].camera_move.move_type == "slow_push_in"
    assert plan.scenes[0].objects[1].role == "hero_subject"
    assert plan.scenes[0].audio_layers[0].role == "ambient_room"
    assert plan.scenes[1].dominant_focal_role == "supporting_subject"
    assert plan.scenes[1].camera_move.move_type == "slight_pan_right"
    assert plan.scenes[1].objects[1].role == "supporting_subject"
    assert plan.audio_plan.layers[0].role == "impact"


def test_placeholder_audio_layers_without_assets_are_allowed() -> None:
    payload = valid_plan_dict()
    payload["audio_plan"]["layers"] = [  # type: ignore[index]
        {
            "audio_id": f"placeholder_audio_{index}",
            "asset_id": None,
            "role": role,
            "start_time": 0.0,
            "end_time": 6.5,
            "volume": 0.25,
            "fade_in": 0.0,
            "fade_out": 0.2,
            "sync_points": [],
        }
        for index, role in enumerate(
            [
                "ambient rhythmic kitchen bed",
                "ingredient placement foley",
                "payoff accent",
                "impact",
                "ambient_room",
            ]
        )
    ]
    payload["provenance"]["rejected_assets"].append(  # type: ignore[index]
        {
            "asset_id": "sizzle_audio",
            "reason": "Placeholder audio is used because no selected audio asset matches the planned bed.",
        }
    )

    plan = CinematicReelPlan.model_validate(payload)

    assert [layer.asset_id for layer in plan.audio_plan.layers] == [None, None, None, None, None]
    assert [layer.role for layer in plan.audio_plan.layers] == [
        "ambient_room",
        "impact",
        "impact",
        "impact",
        "ambient_room",
    ]


def test_non_placeholder_audio_layers_without_assets_are_rejected() -> None:
    payload = valid_plan_dict()
    payload["audio_plan"]["layers"][0]["asset_id"] = None  # type: ignore[index]
    payload["audio_plan"]["layers"][0]["audio_id"] = "ambient_bed"  # type: ignore[index]

    with pytest.raises(ValidationError, match="known audio roles require asset_id"):
        CinematicReelPlan.model_validate(payload)


def test_unknown_shadow_light_references_are_repaired_to_declared_light() -> None:
    payload = valid_plan_dict()
    first_scene = payload["scenes"][0]  # type: ignore[index]
    first_scene["objects"][0]["object_id"] = "hook_background_plate"  # type: ignore[index]
    first_scene["objects"][0]["shadow_spec"]["enabled"] = True  # type: ignore[index]
    first_scene["objects"][0]["shadow_spec"]["source_light_id"] = "missing_softbox"  # type: ignore[index]
    first_scene["objects"][0]["shadow_spec"]["contact_shadow_required"] = False  # type: ignore[index]
    payload["lighting_shadow_plan"]["per_object_shadow_specs"][0][  # type: ignore[index]
        "object_id"
    ] = "hook_background_plate"
    payload["lighting_shadow_plan"]["per_object_shadow_specs"][0][  # type: ignore[index]
        "enabled"
    ] = True
    payload["lighting_shadow_plan"]["per_object_shadow_specs"][0][  # type: ignore[index]
        "source_light_id"
    ] = "missing_softbox"

    plan = CinematicReelPlan.model_validate(payload)

    assert plan.scenes[0].objects[0].object_id == "hook_background_plate"
    assert plan.scenes[0].objects[0].shadow_spec.source_light_id == "key_window"
    assert plan.lighting_shadow_plan.per_object_shadow_specs[0].source_light_id == "key_window"


def test_tiny_hero_and_supporting_subjects_are_resized_before_realism_qa() -> None:
    payload = valid_plan_dict()
    scene_1 = payload["scenes"][0]  # type: ignore[index]
    scene_2 = payload["scenes"][1]  # type: ignore[index]
    for item in (scene_1["objects"][1], scene_2["objects"][1]):  # type: ignore[index]
        item["width_normalised"] = 0.04
        item["height_normalised"] = 0.04
        item["scale"] = 0.2
    scene_1["objects"][2]["role"] = "supporting_subject"  # type: ignore[index]
    scene_1["objects"][2]["width_normalised"] = 0.03  # type: ignore[index]
    scene_1["objects"][2]["height_normalised"] = 0.03  # type: ignore[index]
    scene_1["objects"][2]["scale"] = 0.25  # type: ignore[index]
    scene_1["objects"][2]["shadow_spec"]["enabled"] = True  # type: ignore[index]
    scene_1["objects"][2]["shadow_spec"]["source_light_id"] = "key_window"  # type: ignore[index]
    scene_1["objects"][2]["shadow_spec"]["contact_shadow_required"] = True  # type: ignore[index]

    plan = CinematicReelPlan.model_validate(payload)
    assert all(
        item.width_normalised * item.height_normalised * item.scale * item.scale >= 0.015
        for scene in plan.scenes
        for item in scene.objects
        if item.role in {"hero_subject", "supporting_subject"}
    )
    assert all(
        item.scale >= 1.0
        for scene in plan.scenes
        for item in scene.objects
        if item.role in {"hero_subject", "supporting_subject"}
    )


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


def test_external_generation_process_language_is_sanitized() -> None:
    payload = valid_plan_dict()
    payload["render_notes"] = [
        "Call Runway to create video for the final beat.",
        "Use uploaded text file and do not request a screenshot.",
    ]
    payload["global_camera_style"] = "Do not generate image or copy existing reel."
    payload["scenes"][0]["purpose"] = "Avoid external video API calls."  # type: ignore[index]
    payload["scenes"][0]["objects"][0][  # type: ignore[index]
        "realism_reason"
    ] = "Use this as a screenshot-style background reference."

    validated = validate_pasted_cinematic_plan(payload, planner_input=_planner_input())
    material = " ".join(
        [
            validated.plan.global_camera_style,
            *validated.plan.render_notes,
            *(scene.purpose for scene in validated.plan.scenes),
            *(item.realism_reason for scene in validated.plan.scenes for item in scene.objects),
        ]
    ).lower()

    assert "call runway" not in material
    assert "create video" not in material
    assert "generate image" not in material
    assert "external video api" not in material
    assert "screenshot" not in material
    assert "copy existing reel" not in material


def test_extra_high_priority_scene_objects_are_demoted_before_regulation() -> None:
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

    assert report.passed
    assert [item.role for item in plan.scenes[0].objects].count("hero_subject") == 1
    assert "too_many_high_priority_objects" not in report.as_dict()["failure_codes"]


def test_missing_dominant_subject_fails_validation() -> None:
    payload = valid_plan_dict()
    payload["scenes"][0]["dominant_focal_role"] = "brand_marker"  # type: ignore[index]

    with pytest.raises(ValidationError, match="dominant_focal_role"):
        CinematicReelPlan.model_validate(payload)
