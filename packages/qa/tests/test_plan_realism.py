from __future__ import annotations

import copy

from content_lab_creative.planning_schema import CinematicReelPlan
from content_lab_qa.plan_realism import validate_cinematic_plan_realism


def _motion() -> dict[str, object]:
    return {
        "type": "linear",
        "start_value": {"x": 0.5, "scale": 1.0},
        "end_value": {"x": 0.5, "scale": 1.03},
        "easing": "ease_in_out",
        "jitter_allowed": False,
        "speed": 0.2,
        "sync_to_audio": None,
    }


def _shadow(enabled: bool, *, contact: bool = False) -> dict[str, object]:
    return {
        "enabled": enabled,
        "source_light_id": "key_window" if enabled else None,
        "offset_x": 0.03 if enabled else 0.0,
        "offset_y": 0.05 if enabled else 0.0,
        "blur": 0.22 if contact else 0.55,
        "opacity": 0.4 if enabled else 0.0,
        "softness": 0.55 if contact else 0.9,
        "derived_from_z_depth": True,
        "contact_shadow_required": contact,
    }


def _object(
    object_id: str,
    role: str,
    asset_id: str,
    z: float,
    shadow: dict[str, object],
) -> dict[str, object]:
    return {
        "object_id": object_id,
        "asset_id": asset_id,
        "asset_label": object_id,
        "role": role,
        "scene_id": "scene_1",
        "start_time": 0.0,
        "end_time": 6.0,
        "x": 0.5,
        "y": 0.5,
        "z": z,
        "scale": 1.0,
        "width_normalised": 0.62 if role == "hero_subject" else 1.0,
        "height_normalised": 0.42 if role == "hero_subject" else 1.0,
        "rotation": 0.0,
        "opacity": 1.0,
        "anchor_point": "center",
        "motion_curve": _motion(),
        "shadow_spec": shadow,
        "blur_spec": {"radius": 0.0, "background_blur": 0.0, "motion_blur": 0.02},
        "occlusion_group": "scene_1_table",
        "realism_reason": "Object is placed to support one coherent filmed scene.",
    }


def _valid_plan_dict() -> dict[str, object]:
    objects = [
        _object("kitchen_bg", "environment_base", "kitchen_bg", 0.05, _shadow(False)),
        _object("steak_hero", "hero_subject", "steak_clip", 0.72, _shadow(True, contact=True)),
    ]
    return {
        "plan_id": "plan_qa",
        "page_context_summary": "Kitchen Lab makes sensory cooking reels.",
        "content_goal": "Make steak prep appetising.",
        "selected_prompt_paths": ["sensory_hook", "cinematic_closeup"],
        "narrative_arc": {
            "hook": "Open on sizzle.",
            "development": "Push through steam.",
            "reveal_payoff": "Show the steak texture.",
            "closing_retention_loop": "Hold a loopable glisten.",
        },
        "total_duration_seconds": 6.0,
        "fps": 24,
        "canvas": {"aspect_ratio": "9:16", "width": 1080, "height": 1920},
        "scenes": [
            {
                "scene_id": "scene_1",
                "start_time": 0.0,
                "end_time": 6.0,
                "purpose": "One coherent kitchen closeup.",
                "dominant_focal_role": "hero_subject",
                "emotional_intent": "Sensory focus.",
                "visual_density": "low",
                "camera_move": {
                    "move_type": "slow_push_in",
                    "start_time": 0.0,
                    "end_time": 6.0,
                    "crop_x": 0.5,
                    "crop_y": 0.5,
                    "zoom": 1.05,
                    "rotation": 0.0,
                    "shake_intensity": 0.02,
                    "shake_frequency": 6.0,
                    "motion_curve": _motion(),
                },
                "objects": objects,
                "captions": [
                    {
                        "caption_id": "cap_1",
                        "text": "That first sizzle matters",
                        "role": "hook",
                        "start_time": 0.4,
                        "end_time": 1.8,
                        "x": 0.5,
                        "y": 0.14,
                        "max_width": 0.72,
                        "font_size": 54,
                        "weight": "bold",
                        "alignment": "center",
                        "animation": "fade_up",
                        "safe_area": {
                            "top": 0.08,
                            "right": 0.06,
                            "bottom": 0.08,
                            "left": 0.06,
                        },
                        "safe_area_compliant": True,
                        "renderer_text_only": True,
                    }
                ],
                "audio_layers": [],
                "transition_in": None,
                "transition_out": "loop",
            }
        ],
        "global_camera_style": "Slow closeup push.",
        "global_lighting_style": "Warm window light.",
        "caption_strategy": "Short safe captions.",
        "audio_strategy": "Sizzle as sensory anchor.",
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
            "per_object_shadow_specs": [
                {"object_id": item["object_id"], **item["shadow_spec"]} for item in objects
            ],
            "global_colour_temperature": 4300,
            "contrast_level": "medium",
        },
        "audio_plan": {"layers": [], "sync_points": [], "sensory_moments": ["0.2s sizzle"]},
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
        "render_notes": ["Use stored registry assets only."],
        "provenance": {
            "input_page_context_hash": "a" * 64,
            "selected_asset_ids": ["kitchen_bg", "steak_clip"],
            "selected_prompt_paths": ["sensory_hook", "cinematic_closeup"],
            "planning_prompt_version": "single_prompt_cinematic_reel_planner_v1",
            "plan_hash": "",
            "rejected_assets": [],
            "realism_risk_score": 0.2,
        },
    }


def test_plan_realism_accepts_coherent_cinematic_plan() -> None:
    plan = CinematicReelPlan.model_validate(_valid_plan_dict())

    report = validate_cinematic_plan_realism(plan)

    assert report.passed is True


def test_plan_realism_rejects_too_many_equal_priority_foreground_objects() -> None:
    payload = _valid_plan_dict()
    scene = payload["scenes"][0]  # type: ignore[index]
    extra_a = copy.deepcopy(scene["objects"][1])
    extra_a["object_id"] = "extra_hero_a"
    extra_b = copy.deepcopy(scene["objects"][1])
    extra_b["object_id"] = "extra_hero_b"
    scene["objects"].extend([extra_a, extra_b])
    payload["lighting_shadow_plan"]["per_object_shadow_specs"].extend(  # type: ignore[index]
        [
            {"object_id": extra_a["object_id"], **extra_a["shadow_spec"]},
            {"object_id": extra_b["object_id"], **extra_b["shadow_spec"]},
        ]
    )
    plan = CinematicReelPlan.model_validate(payload)

    report = validate_cinematic_plan_realism(plan)

    assert not report.passed
    assert "too_many_equal_priority_foreground_objects" in report.as_dict()["failure_codes"]


def test_plan_realism_rejects_depth_and_shadow_incoherence() -> None:
    payload = _valid_plan_dict()
    scene = payload["scenes"][0]  # type: ignore[index]
    scene["objects"][0]["z"] = 0.9
    scene["objects"][1]["shadow_spec"] = _shadow(False)
    plan = CinematicReelPlan.model_validate(payload)

    report = validate_cinematic_plan_realism(plan)

    assert not report.passed
    assert "depth_order_inconsistent" in report.as_dict()["failure_codes"]
    assert "missing_contact_shadow" in report.as_dict()["failure_codes"]
