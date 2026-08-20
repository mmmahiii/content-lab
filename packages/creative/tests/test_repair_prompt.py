from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from content_lab_creative.repair_prompt import (
    PlannerValidationFinding,
    PlannerValidationReport,
    analyze_cinematic_plan_validation,
    build_repair_prompt,
)
from content_lab_creative.single_prompt_reel_planner import validate_pasted_cinematic_plan

_SPEC = importlib.util.spec_from_file_location(
    "_spr_tests",
    Path(__file__).resolve().parent / "test_single_prompt_reel_planner.py",
)
assert _SPEC and _SPEC.loader
_spr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_spr)


def test_repair_prompt_lists_validator_failure_codes() -> None:
    planner_input = _spr._planner_input()
    payload = copy.deepcopy(_spr.valid_plan_dict())
    hero = next(o for o in payload["scenes"][0]["objects"] if o["role"] == "hero_subject")  # type: ignore[index]
    hero["z"] = 0.12

    raw_text = json.dumps(payload)
    report = analyze_cinematic_plan_validation(raw_text, planner_input=planner_input)
    assert report.passed is False
    assert "foreground_too_far_back" in report.failure_codes()

    repair = build_repair_prompt(
        planner_input=planner_input,
        invalid_plan_json_text=raw_text,
        validation_report=report,
    )
    assert "foreground_too_far_back" in repair
    assert '"failure_codes"' in repair


def test_repair_prompt_forbids_new_assets_and_preserves_selected_ids() -> None:
    planner_input = _spr._planner_input()
    payload = copy.deepcopy(_spr.valid_plan_dict())
    hero = next(o for o in payload["scenes"][0]["objects"] if o["role"] == "hero_subject")  # type: ignore[index]
    hero["z"] = 0.11

    raw_text = json.dumps(payload)
    report = analyze_cinematic_plan_validation(raw_text, planner_input=planner_input)
    repair = build_repair_prompt(
        planner_input=planner_input,
        invalid_plan_json_text=raw_text,
        validation_report=report,
    )
    lowered = repair.lower()
    assert "do not invent asset_ids" in lowered
    assert "must remain exactly" in lowered
    for asset_id in planner_input.selected_asset_ids:
        assert asset_id in repair


def test_repair_prompt_contains_background_reveal_numeric_rules() -> None:
    planner_input = _spr._planner_input()
    report = PlannerValidationReport(
        passed=False,
        findings=(
            PlannerValidationFinding(
                code="background_reveal_overlaps_hero",
                severity="fail",
                message="obj_plant_accent overlaps hero_subject by 0.48.",
                suggested_fix="Move it to a rear side region.",
                scene_id="scene_02",
                details={"object_id": "obj_plant_accent"},
            ),
        ),
    )

    repair = build_repair_prompt(
        planner_input=planner_input,
        invalid_plan_json_text=json.dumps(_spr.valid_plan_dict()),
        validation_report=report,
    )

    assert "Background_reveal numeric repair rules" in repair
    assert "z <= 0.45" in repair
    assert "upper_left" in repair


def test_invalid_plan_repairs_to_valid_product_card_layout() -> None:
    planner_input = _spr._planner_input()
    payload = copy.deepcopy(_spr.valid_plan_dict())
    hero = next(o for o in payload["scenes"][0]["objects"] if o["role"] == "hero_subject")  # type: ignore[index]
    hero["z"] = 0.18

    raw_invalid = json.dumps(payload)
    report = analyze_cinematic_plan_validation(raw_invalid, planner_input=planner_input)
    assert report.passed is False

    repaired_dict = json.loads(raw_invalid)
    repaired_dict["render_strategy"] = "product_card_layout"
    repaired_dict["selected_prompt_paths"] = ["sensory_hook", "cinematic_closeup", "object_story"]
    repaired_dict["provenance"]["selected_prompt_paths"] = repaired_dict["selected_prompt_paths"]
    repaired_dict["page_context_summary"] = (
        "Product-forward tabletop clarity without implying filmed physics beyond selected PNG inventory."
    )
    hero_fixed = next(o for o in repaired_dict["scenes"][0]["objects"] if o["role"] == "hero_subject")
    hero_fixed["z"] = 0.74

    repaired_json = json.dumps(repaired_dict)
    report_after = analyze_cinematic_plan_validation(repaired_json, planner_input=planner_input)
    assert report_after.passed is True

    validated = validate_pasted_cinematic_plan(repaired_json, planner_input=planner_input)
    assert validated.plan.render_strategy == "product_card_layout"


def test_analyze_passed_matches_validate_success_path() -> None:
    planner_input = _spr._planner_input()
    raw_ok = json.dumps(_spr.valid_plan_dict())
    report = analyze_cinematic_plan_validation(raw_ok, planner_input=planner_input)
    assert report.passed is True
    validate_pasted_cinematic_plan(raw_ok, planner_input=planner_input)
