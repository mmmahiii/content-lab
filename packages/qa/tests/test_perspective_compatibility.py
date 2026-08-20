from __future__ import annotations

import copy

from content_lab_qa.perspective import validate_perspective_compatibility
from tests.test_scene_coherence import _plan


def _perspective_plan():
    plan = _plan()
    support = plan.scenes[0].objects[0]
    hero = plan.scenes[0].objects[1]
    support.view_angle = "top_down"
    support.surface_plane = "horizontal"
    support.lighting_direction = "upper_left"
    hero.view_angle = "top_down"
    hero.surface_plane = "horizontal"
    hero.lighting_direction = "upper_left"
    hero.spatial_relationship = "on_surface"
    hero.support_object_id = support.object_id
    plan.global_lighting_style = "upper left softbox"
    return plan


def test_top_down_base_and_top_down_object_passes() -> None:
    report = validate_perspective_compatibility(_perspective_plan())

    assert report.passed is True


def test_top_down_base_and_front_facing_object_fails_in_realistic_mode() -> None:
    plan = _perspective_plan()
    plan.scenes[0].objects[1].view_angle = "front"

    report = validate_perspective_compatibility(plan)

    assert not report.passed
    assert "view_angle_mismatch" in report.as_dict()["failure_codes"]


def test_background_reveal_with_foreground_z_fails() -> None:
    plan = _perspective_plan()
    reveal = copy.deepcopy(plan.scenes[0].objects[0])
    reveal.object_id = "reveal"
    reveal.asset_id = "reveal"
    reveal.role = "background_reveal"
    reveal.z = 0.8
    plan.scenes[0].objects.append(reveal)

    report = validate_perspective_compatibility(plan)

    assert not report.passed
    assert "background_reveal_foreground_depth" in report.as_dict()["failure_codes"]


def test_mismatched_known_lighting_direction_increases_risk() -> None:
    plan = _perspective_plan()
    plan.scenes[0].objects[1].lighting_direction = "upper_right"

    report = validate_perspective_compatibility(plan)

    assert report.realism_risk_delta > 0
    assert "lighting_direction_mismatch" in report.as_dict()["warning_codes"]


def test_unknown_perspective_warns_without_failing() -> None:
    plan = _perspective_plan()
    for item in plan.scenes[0].objects:
        item.view_angle = "unknown"

    report = validate_perspective_compatibility(plan)

    assert report.passed is True
    assert "unknown_perspective_metadata" in report.as_dict()["warning_codes"]


def test_severe_mismatch_suggests_product_card_layout_downgrade() -> None:
    plan = _perspective_plan()
    plan.scenes[0].objects[1].view_angle = "front"

    report = validate_perspective_compatibility(plan)

    assert report.recommended_render_strategy == "product_card_layout"


def test_valid_multi_object_perspective_setup_passes() -> None:
    plan = _perspective_plan()
    support = plan.scenes[0].objects[0]
    prop = copy.deepcopy(plan.scenes[0].objects[1])
    prop.object_id = "prop"
    prop.asset_id = "prop"
    prop.role = "supporting_subject"
    prop.x = 0.35
    prop.scale = 0.6
    prop.view_angle = "three_quarter"
    prop.surface_plane = "horizontal"
    prop.support_object_id = support.object_id
    prop.spatial_relationship = "on_surface"
    plan.scenes[0].objects.append(prop)

    report = validate_perspective_compatibility(plan)

    assert report.passed is True
