from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from content_lab_creative.planning_schema import CinematicReelPlan


def _motion() -> dict[str, object]:
    return {
        "type": "linear",
        "start_value": {"x": 0.5},
        "end_value": {"x": 0.5},
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
        "softness": 0.55,
        "derived_from_z_depth": True,
        "contact_shadow_required": contact,
    }


def _object(object_id: str, role: str, *, z: float, x: float = 0.5) -> dict[str, object]:
    return {
        "object_id": object_id,
        "asset_id": object_id,
        "asset_label": object_id,
        "role": role,
        "scene_id": "scene_1",
        "start_time": 0.0,
        "end_time": 4.0,
        "x": x,
        "y": 0.5,
        "z": z,
        "scale": 1.0,
        "width_normalised": 0.45 if role == "hero_subject" else 0.9,
        "height_normalised": 0.35 if role == "hero_subject" else 0.9,
        "rotation": 0.0,
        "opacity": 1.0,
        "anchor_point": "center",
        "motion_curve": _motion(),
        "shadow_spec": _shadow(role != "environment_base", contact=role == "hero_subject"),
        "blur_spec": {"radius": 0.0, "background_blur": 0.0, "motion_blur": 0.0},
        "occlusion_group": "scene_1",
        "realism_reason": "Generic coherent placement.",
    }


def _plan() -> dict[str, object]:
    objects = [
        _object("surface", "environment_base", z=0.05),
        _object("hero", "hero_subject", z=0.7),
    ]
    return {
        "plan_id": "relationship_plan",
        "page_context_summary": "Generic product scene.",
        "content_goal": "Show a product clearly.",
        "selected_prompt_paths": ["sensory_hook"],
        "narrative_arc": {
            "hook": "Open on product.",
            "development": "Show context.",
            "reveal_payoff": "Reveal the detail.",
            "closing_retention_loop": "Loop cleanly.",
        },
        "total_duration_seconds": 4.0,
        "fps": 24,
        "canvas": {"aspect_ratio": "9:16", "width": 1080, "height": 1920},
        "scenes": [
            {
                "scene_id": "scene_1",
                "start_time": 0.0,
                "end_time": 4.0,
                "purpose": "One coherent setup.",
                "dominant_focal_role": "hero_subject",
                "emotional_intent": "Clear focus.",
                "visual_density": "low",
                "camera_move": {
                    "move_type": "static_lockoff",
                    "start_time": 0.0,
                    "end_time": 4.0,
                    "crop_x": 0.5,
                    "crop_y": 0.5,
                    "zoom": 1.0,
                    "rotation": 0.0,
                    "shake_intensity": 0.0,
                    "shake_frequency": 0.0,
                    "motion_curve": _motion(),
                },
                "objects": objects,
                "captions": [],
                "audio_layers": [],
                "transition_in": None,
                "transition_out": None,
            }
        ],
        "global_camera_style": "Locked camera.",
        "global_lighting_style": "Soft window light.",
        "caption_strategy": "Minimal captions.",
        "audio_strategy": "Quiet bed.",
        "lighting_shadow_plan": {
            "lights": [
                {
                    "light_id": "key_window",
                    "type": "window",
                    "x": 0.2,
                    "y": 0.1,
                    "z": 0.9,
                    "intensity": 1.0,
                    "colour_temperature": 4300,
                    "softness": 0.8,
                }
            ],
            "per_object_shadow_specs": [
                {"object_id": item["object_id"], **item["shadow_spec"]} for item in objects
            ],
            "global_colour_temperature": 4300,
            "contrast_level": "medium",
        },
        "audio_plan": {"layers": [], "sync_points": [], "sensory_moments": []},
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
        "render_notes": ["Use stored assets only."],
        "provenance": {
            "input_page_context_hash": "a" * 64,
            "selected_asset_ids": ["surface", "hero"],
            "selected_prompt_paths": ["sensory_hook"],
            "planning_prompt_version": "single_prompt_cinematic_reel_planner_v1",
            "plan_hash": "",
            "rejected_assets": [],
            "realism_risk_score": 0.2,
        },
    }


def test_on_surface_relationship_requires_support_object_id() -> None:
    payload = _plan()
    payload["scenes"][0]["objects"][1]["spatial_relationship"] = "on_surface"  # type: ignore[index]

    with pytest.raises(ValidationError, match="requires support_object_id"):
        CinematicReelPlan.model_validate(payload)


def test_unknown_support_object_id_fails_scene_validation() -> None:
    payload = _plan()
    hero = payload["scenes"][0]["objects"][1]  # type: ignore[index]
    hero["spatial_relationship"] = "on_surface"
    hero["support_object_id"] = "missing"
    hero["required_overlap_ratio"] = 0.1

    with pytest.raises(ValidationError, match="unknown object"):
        CinematicReelPlan.model_validate(payload)


def test_inside_relationship_requires_minimum_overlap() -> None:
    payload = _plan()
    hero = payload["scenes"][0]["objects"][1]  # type: ignore[index]
    hero["spatial_relationship"] = "inside"
    hero["support_object_id"] = "surface"
    hero["required_overlap_ratio"] = 0.2

    with pytest.raises(ValidationError, match="inside relationship requires"):
        CinematicReelPlan.model_validate(payload)


def test_behind_hero_geometry_is_left_to_structured_qa() -> None:
    payload = _plan()
    reveal = _object("reveal", "background_reveal", z=0.8, x=0.1)
    reveal["relative_depth_rule"] = "behind_hero"
    payload["scenes"][0]["objects"].append(reveal)  # type: ignore[index]
    payload["provenance"]["selected_asset_ids"] = ["surface", "hero", "reveal"]  # type: ignore[index]
    payload["lighting_shadow_plan"]["per_object_shadow_specs"].append(  # type: ignore[index]
        {"object_id": "reveal", **reveal["shadow_spec"]}
    )

    plan = CinematicReelPlan.model_validate(payload)

    assert plan.scenes[0].objects[-1].object_id == "reveal"


def test_background_reveal_overlap_geometry_is_left_to_structured_qa() -> None:
    payload = _plan()
    reveal = _object("reveal", "background_reveal", z=0.2, x=0.5)
    payload["scenes"][0]["objects"].append(reveal)  # type: ignore[index]
    payload["provenance"]["selected_asset_ids"] = ["surface", "hero", "reveal"]  # type: ignore[index]
    payload["lighting_shadow_plan"]["per_object_shadow_specs"].append(  # type: ignore[index]
        {"object_id": "reveal", **reveal["shadow_spec"]}
    )

    plan = CinematicReelPlan.model_validate(payload)

    assert plan.scenes[0].objects[-1].role == "background_reveal"


def test_atmospheric_object_can_have_no_support_object() -> None:
    payload = _plan()
    mist = _object("mist", "atmospheric_layer", z=0.55, x=0.2)
    mist["spatial_relationship"] = "atmospheric"
    mist["shadow_spec"] = _shadow(False)
    payload["scenes"][0]["objects"].append(mist)  # type: ignore[index]
    payload["provenance"]["selected_asset_ids"] = ["surface", "hero", "mist"]  # type: ignore[index]
    payload["lighting_shadow_plan"]["per_object_shadow_specs"].append(  # type: ignore[index]
        {"object_id": "mist", **mist["shadow_spec"]}
    )

    plan = CinematicReelPlan.model_validate(payload)

    assert plan.scenes[0].objects[-1].support_object_id is None


def test_contact_shadow_required_object_must_have_target() -> None:
    payload = _plan()
    hero = payload["scenes"][0]["objects"][1]  # type: ignore[index]
    hero["support_contact_required"] = True

    with pytest.raises(ValidationError, match="contact_shadow_target_object_id"):
        CinematicReelPlan.model_validate(payload)


def test_support_overlap_auto_repaired_when_hero_misplaced() -> None:
    payload = _plan()
    hero = payload["scenes"][0]["objects"][1]  # type: ignore[index]
    hero["spatial_relationship"] = "on_surface"
    hero["support_object_id"] = "surface"
    hero["required_overlap_ratio"] = 0.35
    hero["x"] = 0.92
    hero["y"] = 0.92

    plan = CinematicReelPlan.model_validate(copy.deepcopy(payload))

    hero_obj = plan.scenes[0].objects[1]
    assert hero_obj.support_object_id == "surface"
    assert hero_obj.required_overlap_ratio <= 0.35


def test_support_overlap_requirement_relaxed_when_geometrically_impossible() -> None:
    payload = _plan()
    hero = payload["scenes"][0]["objects"][1]  # type: ignore[index]
    hero["spatial_relationship"] = "on_surface"
    hero["support_object_id"] = "surface"
    hero["required_overlap_ratio"] = 0.95
    hero["scale"] = 5.0
    hero["width_normalised"] = 1.0
    hero["height_normalised"] = 1.0

    plan = CinematicReelPlan.model_validate(copy.deepcopy(payload))

    hero_obj = plan.scenes[0].objects[1]
    assert hero_obj.required_overlap_ratio < 0.95


def test_valid_relationship_graph_passes() -> None:
    payload = _plan()
    hero = payload["scenes"][0]["objects"][1]  # type: ignore[index]
    hero["spatial_relationship"] = "on_surface"
    hero["support_object_id"] = "surface"
    hero["required_overlap_ratio"] = 0.1
    hero["support_contact_required"] = True
    hero["contact_shadow_target_object_id"] = "surface"
    hero["relative_depth_rule"] = "above_support"
    hero["relationship_reason"] = "Hero product sits on the base surface."

    plan = CinematicReelPlan.model_validate(copy.deepcopy(payload))

    assert plan.scenes[0].objects[1].support_object_id == "surface"
