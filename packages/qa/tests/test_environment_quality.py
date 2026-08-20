from __future__ import annotations

from content_lab_qa.environment_quality import (
    environment_base_full_frame_eligible,
    validate_environment_quality,
)
from tests.test_scene_coherence import _plan, _valid_plan_dict


def test_301x167_environment_fails_sharp_full_frame_eligibility() -> None:
    assert environment_base_full_frame_eligible(301, 167) is False


def test_1080x1920_environment_passes_sharp_full_frame_eligibility() -> None:
    assert environment_base_full_frame_eligible(1080, 1920) is True


def test_low_res_environment_allowed_only_as_blurred_texture_backdrop() -> None:
    payload = _valid_plan_dict()
    payload["render_strategy"] = "low_res_texture_backdrop"
    payload["scenes"][0]["objects"][0]["source_width"] = 301  # type: ignore[index]
    payload["scenes"][0]["objects"][0]["source_height"] = 167  # type: ignore[index]
    plan = _plan(payload)

    report = validate_environment_quality(plan)

    assert report.passed is True
    assert "low_res_environment_texture_only" in report.as_dict()["warning_codes"]


def test_realistic_plan_using_low_res_full_frame_base_fails() -> None:
    payload = _valid_plan_dict()
    payload["render_strategy"] = "realistic_single_scene"
    payload["scenes"][0]["objects"][0]["source_width"] = 301  # type: ignore[index]
    payload["scenes"][0]["objects"][0]["source_height"] = 167  # type: ignore[index]
    payload["scenes"][0]["objects"][0]["width_normalised"] = 1.0  # type: ignore[index]
    payload["scenes"][0]["objects"][0]["height_normalised"] = 1.0  # type: ignore[index]
    plan = _plan(payload)

    report = validate_environment_quality(plan)

    assert not report.passed
    assert "low_res_environment_full_frame" in report.as_dict()["failure_codes"]


def test_low_res_texture_backdrop_strategy_passes_with_warning() -> None:
    payload = _valid_plan_dict()
    payload["render_strategy"] = "low_res_texture_backdrop"
    payload["scenes"][0]["objects"][0]["source_width"] = 301  # type: ignore[index]
    payload["scenes"][0]["objects"][0]["source_height"] = 167  # type: ignore[index]
    plan = _plan(payload)

    report = validate_environment_quality(plan)

    assert report.passed is True
    assert "render_strategy_downgraded_for_environment" in report.as_dict()["warning_codes"]


def test_no_valid_environment_base_triggers_product_card_layout_downgrade() -> None:
    plan = _plan()
    plan.scenes[0].objects = [item for item in plan.scenes[0].objects if item.role != "environment_base"]

    report = validate_environment_quality(plan)

    assert not report.passed
    assert report.recommended_render_strategy == "product_card_layout"
    assert "missing_valid_environment_base" in report.as_dict()["failure_codes"]


def test_render_notes_include_low_res_handling_instructions() -> None:
    payload = _valid_plan_dict()
    payload["render_strategy"] = "low_res_texture_backdrop"
    payload["render_notes"] = []
    payload["scenes"][0]["objects"][0]["source_width"] = 301  # type: ignore[index]
    payload["scenes"][0]["objects"][0]["source_height"] = 167  # type: ignore[index]
    plan = _plan(payload)

    assert any("Low-res environment handling" in note for note in plan.render_notes)
