from __future__ import annotations

import copy

from content_lab_creative.planning_schema import CinematicReelPlan
from content_lab_editing.support_surface_overlap import (
    OverlapValidationContext,
    PlacementOverlapArtifacts,
    SupportSurfaceMask,
)
from content_lab_qa.scene_coherence import validate_scene_coherence


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


def _object(
    object_id: str,
    role: str,
    *,
    z: float,
    x: float = 0.5,
    scale: float = 1.0,
) -> dict[str, object]:
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
        "scale": scale,
        "width_normalised": 0.45 if role == "hero_subject" else 0.25,
        "height_normalised": 0.35 if role == "hero_subject" else 0.2,
        "rotation": 0.0,
        "opacity": 1.0,
        "anchor_point": "center",
        "motion_curve": _motion(),
        "shadow_spec": _shadow(
            role not in {"environment_base", "atmospheric_layer"},
            contact=role in {"hero_subject", "supporting_subject", "foreground_texture"},
        ),
        "blur_spec": {"radius": 0.0, "background_blur": 0.0, "motion_blur": 0.0},
        "occlusion_group": "scene_1",
        "realism_reason": "Generic coherent placement.",
    }


def _valid_plan_dict() -> dict[str, object]:
    surface = _object("surface", "environment_base", z=0.05, scale=2.0)
    hero = _object("hero", "hero_subject", z=0.72, scale=1.2)
    hero.update(
        {
            "spatial_relationship": "on_surface",
            "support_object_id": "surface",
            "required_overlap_ratio": 0.1,
            "support_contact_required": True,
            "contact_shadow_target_object_id": "surface",
            "relative_depth_rule": "above_support",
            "relationship_reason": "Hero sits on the base surface.",
        }
    )
    objects = [surface, hero]
    return {
        "plan_id": "scene_coherence_plan",
        "page_context_summary": "Generic visual plan.",
        "content_goal": "Show one clear hero.",
        "selected_prompt_paths": ["sensory_hook"],
        "narrative_arc": {
            "hook": "Open on hero.",
            "development": "Show context.",
            "reveal_payoff": "Reveal detail.",
            "closing_retention_loop": "Loop.",
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
                "emotional_intent": "Focus.",
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
                "captions": [
                    {
                        "caption_id": "cap_1",
                        "text": "Clean detail",
                        "role": "hook",
                        "start_time": 0.2,
                        "end_time": 1.5,
                        "x": 0.5,
                        "y": 0.12,
                        "max_width": 0.6,
                        "font_size": 48,
                        "weight": "bold",
                        "alignment": "center",
                        "animation": "fade_up",
                        "safe_area": {"top": 0.08, "right": 0.06, "bottom": 0.08, "left": 0.06},
                        "safe_area_compliant": True,
                        "renderer_text_only": True,
                    }
                ],
                "audio_layers": [],
                "transition_in": None,
                "transition_out": None,
            }
        ],
        "global_camera_style": "Locked camera.",
        "global_lighting_style": "Soft light.",
        "caption_strategy": "Avoid hero.",
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


def _plan(payload: dict[str, object] | None = None) -> CinematicReelPlan:
    return CinematicReelPlan.model_validate(payload or _valid_plan_dict())


def _codes(plan: CinematicReelPlan) -> set[str]:
    return set(validate_scene_coherence(plan).as_dict()["failure_codes"])


def test_scene_with_no_environment_base_fails() -> None:
    plan = _plan()
    plan.scenes[0].objects = [item for item in plan.scenes[0].objects if item.role != "environment_base"]

    assert "missing_environment_base" in _codes(plan)


def test_scene_with_two_hero_subjects_fails() -> None:
    plan = _plan()
    extra = copy.deepcopy(plan.scenes[0].objects[1])
    extra.object_id = "hero_2"
    extra.asset_id = "hero_2"
    plan.scenes[0].objects.append(extra)

    assert "too_many_hero_subjects" in _codes(plan)


def test_scene_with_too_many_foreground_objects_fails() -> None:
    plan = _plan()
    for index in range(4):
        item = copy.deepcopy(plan.scenes[0].objects[1])
        item.object_id = f"support_{index}"
        item.asset_id = f"support_{index}"
        item.role = "supporting_subject"
        item.support_object_id = "surface"
        plan.scenes[0].objects.append(item)

    assert "too_many_high_z_foreground_objects" in _codes(plan)


def test_background_reveal_overlapping_hero_too_much_fails() -> None:
    plan = _plan()
    reveal = copy.deepcopy(plan.scenes[0].objects[1])
    reveal.object_id = "reveal"
    reveal.asset_id = "reveal"
    reveal.role = "background_reveal"
    reveal.z = 0.2
    reveal.relative_depth_rule = "behind_hero"
    plan.scenes[0].objects.append(reveal)

    assert "background_reveal_overlaps_hero" in _codes(plan)


def test_background_reveal_in_front_of_hero_fails() -> None:
    plan = _plan()
    reveal = copy.deepcopy(plan.scenes[0].objects[1])
    reveal.object_id = "plant_accent"
    reveal.asset_id = "plant_accent"
    reveal.role = "background_reveal"
    reveal.z = 0.92
    reveal.max_overlap_ratio = 0.1
    reveal.relative_depth_rule = "behind_hero"
    plan.scenes[0].objects.append(reveal)

    report = validate_scene_coherence(plan).as_dict()

    assert "background_reveal_depth_invalid" in report["failure_codes"]
    failure = next(
        item
        for item in report["findings"]
        if item["code"] == "background_reveal_depth_invalid"
    )
    assert failure["details"]["object_id"] == "plant_accent"
    assert "problem" in failure["details"]


def test_background_reveal_outside_allowed_region_fails() -> None:
    plan = _plan()
    reveal = copy.deepcopy(plan.scenes[0].objects[1])
    reveal.object_id = "plant_accent"
    reveal.asset_id = "plant_accent"
    reveal.role = "background_reveal"
    reveal.x = 0.5
    reveal.y = 0.7
    reveal.z = 0.2
    reveal.max_overlap_ratio = 0.1
    reveal.preferred_screen_regions = ["upper_right"]
    reveal.relative_depth_rule = "behind_hero"
    plan.scenes[0].objects.append(reveal)

    assert "background_reveal_region_invalid" in _codes(plan)


def test_background_reveal_foreground_metadata_is_canonicalized_to_rear_regions() -> None:
    payload = _valid_plan_dict()
    reveal = copy.deepcopy(payload["scenes"][0]["objects"][1])  # type: ignore[index]
    reveal.update(
        {
            "object_id": "obj_plant_accent",
            "asset_id": "obj_plant_accent",
            "role": "background_reveal",
            "x": 0.79,
            "y": 0.43,
            "z": 0.2,
            "scale": 0.22,
            "max_overlap_ratio": 0.28,
            "preferred_screen_regions": ["foreground", "lower_third", "side"],
            "forbidden_screen_regions": ["full_frame"],
            "spatial_relationship": "independent",
            "support_object_id": None,
            "required_overlap_ratio": 0.0,
            "support_contact_required": False,
            "contact_shadow_target_object_id": None,
        }
    )
    payload["scenes"][0]["objects"].append(reveal)  # type: ignore[index]
    payload["provenance"]["selected_asset_ids"].append("obj_plant_accent")  # type: ignore[index]

    plan = _plan(payload)
    plant = plan.scenes[0].objects[-1]

    assert plant.preferred_screen_regions == [
        "upper_left",
        "upper_right",
        "background_left",
        "background_right",
        "rear",
        "side",
    ]
    assert plant.forbidden_screen_regions == []
    assert "background_reveal_region_invalid" not in _codes(plan)


def test_repair_flow_can_move_background_reveal_to_valid_position() -> None:
    plan = _plan()
    reveal = copy.deepcopy(plan.scenes[0].objects[1])
    reveal.object_id = "plant_accent"
    reveal.asset_id = "plant_accent"
    reveal.role = "background_reveal"
    reveal.x = 0.82
    reveal.y = 0.22
    reveal.z = 0.2
    reveal.scale = 0.55
    reveal.opacity = 0.65
    reveal.max_overlap_ratio = 0.1
    reveal.spatial_relationship = "independent"
    reveal.support_object_id = None
    reveal.required_overlap_ratio = 0.0
    reveal.support_contact_required = False
    reveal.contact_shadow_target_object_id = None
    reveal.preferred_screen_regions = ["upper_right"]
    reveal.relative_depth_rule = "behind_hero"
    plan.scenes[0].objects.append(reveal)

    assert validate_scene_coherence(plan).passed is True


def test_repair_flow_can_reject_invalid_background_reveal() -> None:
    payload = _valid_plan_dict()
    payload["provenance"]["rejected_assets"] = [
        {"asset_id": "plant_accent", "reason": "Rejected because it overlapped the hero."}
    ]
    plan = _plan(payload)

    assert validate_scene_coherence(plan).passed is True


def test_valid_background_reveal_behind_hero_passes() -> None:
    plan = _plan()
    reveal = copy.deepcopy(plan.scenes[0].objects[1])
    reveal.object_id = "plant_accent"
    reveal.asset_id = "plant_accent"
    reveal.role = "background_reveal"
    reveal.x = 0.82
    reveal.y = 0.22
    reveal.z = 0.2
    reveal.scale = 0.45
    reveal.opacity = 0.6
    reveal.max_overlap_ratio = 0.1
    reveal.spatial_relationship = "independent"
    reveal.support_object_id = None
    reveal.required_overlap_ratio = 0.0
    reveal.support_contact_required = False
    reveal.contact_shadow_target_object_id = None
    reveal.relative_depth_rule = "behind_hero"
    plan.scenes[0].objects.append(reveal)

    assert validate_scene_coherence(plan).passed is True


def test_transparent_cutout_floating_without_support_fails() -> None:
    plan = _plan()
    cutout = copy.deepcopy(plan.scenes[0].objects[1])
    cutout.object_id = "cutout"
    cutout.asset_id = "cutout"
    cutout.role = "foreground_texture"
    cutout.support_object_id = None
    cutout.spatial_relationship = "independent"
    plan.scenes[0].objects.append(cutout)

    assert "floating_cutout_without_support" in _codes(plan)


def test_support_object_competing_with_hero_fails() -> None:
    plan = _plan()
    support = copy.deepcopy(plan.scenes[0].objects[1])
    support.object_id = "big_support"
    support.asset_id = "big_support"
    support.role = "supporting_subject"
    support.scale = 2.0
    support.support_object_id = "surface"
    plan.scenes[0].objects.append(support)

    assert "hero_not_highest_visual_priority" in _codes(plan)


def test_invalid_light_reference_fails() -> None:
    plan = _plan()
    plan.scenes[0].objects[1].shadow_spec.source_light_id = "missing_light"

    assert "invalid_light_reference" in _codes(plan)


def test_caption_overlapping_hero_fails() -> None:
    plan = _plan()
    plan.scenes[0].captions[0].y = 0.5

    assert "caption_overlaps_hero" in _codes(plan)


def test_missing_contact_shadow_fails() -> None:
    plan = _plan()
    hero = plan.scenes[0].objects[1]
    hero.shadow_spec.contact_shadow_required = False

    assert "missing_contact_shadow" in _codes(plan)


def test_valid_coherent_scene_passes() -> None:
    report = validate_scene_coherence(_plan())

    assert report.passed is True


def test_validator_returns_machine_readable_failure_codes() -> None:
    plan = _plan()
    plan.scenes[0].objects = [item for item in plan.scenes[0].objects if item.role != "environment_base"]

    report = validate_scene_coherence(plan)

    assert "missing_environment_base" in report.as_dict()["failure_codes"]


def test_validator_returns_human_readable_suggested_fixes() -> None:
    plan = _plan()
    plan.scenes[0].objects = [item for item in plan.scenes[0].objects if item.role != "environment_base"]

    finding = validate_scene_coherence(plan).findings[0]

    assert finding.suggested_fix
    assert "Add" in finding.suggested_fix


def _hollow_center_mask(width: int, height: int) -> SupportSurfaceMask:
    samples: list[float] = []
    for row in range(height):
        for col in range(width):
            cx = (col + 0.5) / width
            cy = (row + 0.5) / height
            samples.append(1.0 if 0.35 <= cx <= 0.65 and 0.35 <= cy <= 0.65 else 0.0)
    return SupportSurfaceMask(width=width, height=height, samples=tuple(samples))


def test_on_surface_outside_support_region_with_mask_context() -> None:
    plan = _plan()
    surface = plan.scenes[0].objects[0]
    surface.support_surface_mask_uri = "s3://masks/plate.png"
    surface.width_normalised = 0.9
    surface.height_normalised = 0.9
    hero = plan.scenes[0].objects[1]
    hero.x = 0.14
    hero.y = 0.14
    hero.width_normalised = 0.22
    hero.height_normalised = 0.22
    hero.required_overlap_ratio = 0.2
    context = OverlapValidationContext(
        by_mask_uri={
            "s3://masks/plate.png": PlacementOverlapArtifacts(
                support_surface_mask=_hollow_center_mask(8, 8),
            ),
        },
    )

    report = validate_scene_coherence(plan, overlap_context=context)

    assert not report.passed
    assert "on_surface_outside_support_region" in report.as_dict()["failure_codes"]
