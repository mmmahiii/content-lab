from __future__ import annotations

import copy

from content_lab_qa.plan_realism import validate_cinematic_plan_realism
from tests.test_scene_coherence import _plan, _valid_plan_dict


def _failure_codes(plan) -> set[str]:
    return set(validate_cinematic_plan_realism(plan).as_dict()["failure_codes"])


def test_floating_collage_plan_fails() -> None:
    plan = _plan()
    for index in range(4):
        item = copy.deepcopy(plan.scenes[0].objects[1])
        item.object_id = f"floating_{index}"
        item.asset_id = f"floating_{index}"
        item.role = "foreground_texture"
        item.support_object_id = None
        item.spatial_relationship = "independent"
        plan.scenes[0].objects.append(item)

    codes = _failure_codes(plan)

    assert "floating_cutout_without_support" in codes
    assert "too_many_high_z_foreground_objects" in codes


def test_missing_environment_base_fails() -> None:
    plan = _plan()
    plan.scenes[0].objects = [item for item in plan.scenes[0].objects if item.role != "environment_base"]

    assert "missing_environment_base" in _failure_codes(plan)


def test_static_png_only_pack_cannot_use_impossible_sensory_motion() -> None:
    plan = _plan()
    plan.scenes[0].objects[1].motion_curve.type = "liquid_splash_deformation"
    plan.scenes[0].objects[1].realism_reason = "PNG-only asset should not imply liquid motion."

    report = validate_cinematic_plan_realism(plan)

    assert not report.passed
    assert "impossible_static_asset_motion" in report.as_dict()["failure_codes"]


def test_low_resolution_base_forces_downgrade_or_warning() -> None:
    payload = _valid_plan_dict()
    payload["render_strategy"] = "low_res_texture_backdrop"
    payload["scenes"][0]["objects"][0]["source_width"] = 301  # type: ignore[index]
    payload["scenes"][0]["objects"][0]["source_height"] = 167  # type: ignore[index]
    plan = _plan(payload)

    report = validate_cinematic_plan_realism(plan)

    assert report.passed is True
    assert "low_res_environment_texture_only" in report.as_dict()["warning_codes"]


def test_duplicate_role_asset_must_be_rejected_or_fails() -> None:
    plan = _plan()
    duplicate = copy.deepcopy(plan.scenes[0].objects[1])
    duplicate.object_id = "duplicate_hero"
    duplicate.asset_id = "duplicate_hero"
    plan.scenes[0].objects.append(duplicate)

    assert "too_many_hero_subjects" in _failure_codes(plan)


def test_background_reveal_stays_behind_hero() -> None:
    plan = _plan()
    reveal = copy.deepcopy(plan.scenes[0].objects[0])
    reveal.object_id = "reveal"
    reveal.asset_id = "reveal"
    reveal.role = "background_reveal"
    reveal.z = 0.8
    reveal.relative_depth_rule = "behind_hero"
    plan.scenes[0].objects.append(reveal)

    assert "background_reveal_too_forward" in _failure_codes(plan)


def test_hero_remains_visually_dominant() -> None:
    plan = _plan()
    support = copy.deepcopy(plan.scenes[0].objects[1])
    support.object_id = "oversized_support"
    support.asset_id = "oversized_support"
    support.role = "supporting_subject"
    support.scale = 2.0
    support.support_object_id = "surface"
    plan.scenes[0].objects.append(support)

    assert "hero_not_highest_visual_priority" in _failure_codes(plan)


def test_perspective_mismatch_is_caught() -> None:
    plan = _plan()
    plan.scenes[0].objects[0].view_angle = "top_down"
    plan.scenes[0].objects[0].surface_plane = "horizontal"
    plan.scenes[0].objects[1].view_angle = "front"
    plan.scenes[0].objects[1].surface_plane = "vertical"

    assert "view_angle_mismatch" in _failure_codes(plan)


def test_valid_compatible_pack_plan_passes() -> None:
    report = validate_cinematic_plan_realism(_plan())

    assert report.passed is True


def test_render_strategy_is_explicit() -> None:
    assert _plan().render_strategy == "realistic_single_scene"


def test_repaired_plan_passes_after_validator_failure() -> None:
    bad = _plan()
    bad.scenes[0].objects = [item for item in bad.scenes[0].objects if item.role != "environment_base"]
    assert "missing_environment_base" in _failure_codes(bad)

    repaired = _plan()
    assert validate_cinematic_plan_realism(repaired).passed is True


def test_failed_plan_emits_structured_failure_codes() -> None:
    plan = _plan()
    plan.scenes[0].objects = [item for item in plan.scenes[0].objects if item.role != "environment_base"]

    report = validate_cinematic_plan_realism(plan).as_dict()

    assert isinstance(report["failure_codes"], list)
    assert "missing_environment_base" in report["failure_codes"]
