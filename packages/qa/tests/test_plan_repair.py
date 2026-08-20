from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from content_lab_creative.planning_schema import CinematicReelPlan
from content_lab_qa.plan_realism import validate_cinematic_plan_realism
from content_lab_qa.plan_repair import repair_cinematic_plan_for_realism

_SPEC = importlib.util.spec_from_file_location(
    "_plan_realism_fixtures",
    Path(__file__).resolve().parent / "test_plan_realism.py",
)
assert _SPEC and _SPEC.loader
_plan_realism_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_plan_realism_mod)
_valid_plan_dict = _plan_realism_mod._valid_plan_dict


def _static_aggregate() -> dict[str, object]:
    return {
        "static_png_only_pack": True,
        "sensory_hook_evidence": False,
        "physical_motion_claim_evidence": False,
        "satisfying_process_evidence": False,
        "speed_ramp_evidence": False,
        "asset_capabilities": [],
    }


def _capabilities_ok_aggregate() -> dict[str, object]:
    agg = dict(_static_aggregate())
    agg["static_png_only_pack"] = False
    agg["sensory_hook_evidence"] = True
    agg["physical_motion_claim_evidence"] = True
    return agg


def test_repair_removes_prompt_path_claims_and_static_motion_only() -> None:
    payload = copy.deepcopy(_valid_plan_dict())
    payload["narrative_arc"]["hook"] = "Pouring glaze into a sizzling steam moment."
    payload["scenes"][0]["purpose"] = "Sizzling steam closeup without video evidence."
    payload["scenes"][0]["captions"][0]["text"] = "Steam and sizzle"
    payload["scenes"][0]["objects"][1]["motion_curve"]["type"] = "steam_sizzle_push"
    payload["audio_strategy"] = "Silent reel."
    payload["audio_plan"] = {"layers": [], "sync_points": [], "sensory_moments": ["0.2s sizzle"]}
    plan = CinematicReelPlan.model_validate(payload)
    report = validate_cinematic_plan_realism(
        plan,
        prompt_path_capabilities_aggregate=_static_aggregate(),
    )

    repaired = repair_cinematic_plan_for_realism(plan, report)
    repaired_report = validate_cinematic_plan_realism(
        repaired.plan,
        prompt_path_capabilities_aggregate=_static_aggregate(),
    )

    assert repaired.repaired is True
    assert repaired_report.passed is True
    assert repaired.plan.scenes[0].objects[1].motion_curve.type == "linear"
    assert "sizzle" not in repaired.plan.narrative_arc.hook.lower()
    assert "steam" not in repaired.plan.scenes[0].captions[0].text.lower()


def test_repair_does_not_move_or_resize_for_visual_hierarchy() -> None:
    staged = copy.deepcopy(_valid_plan_dict())
    oversized = copy.deepcopy(staged["scenes"][0]["objects"][1])
    oversized["object_id"] = "oversized_support"
    oversized["asset_id"] = "oversized_support"
    oversized["role"] = "supporting_subject"
    oversized["scale"] = 2.0
    staged["scenes"][0]["objects"].append(oversized)
    staged["provenance"]["selected_asset_ids"].append("oversized_support")

    base = CinematicReelPlan.model_validate(staged)
    fail_report = validate_cinematic_plan_realism(
        base,
        prompt_path_capabilities_aggregate=_capabilities_ok_aggregate(),
    )
    assert "hero_not_highest_visual_priority" in fail_report.as_dict()["failure_codes"]

    repaired = repair_cinematic_plan_for_realism(base, fail_report)

    assert repaired.repaired is False
    assert repaired.plan.scenes[0].objects[-1].scale == 2.0


def test_repair_scrubs_prompt_path_claims_without_relabeling_assets() -> None:
    payload = copy.deepcopy(_valid_plan_dict())
    payload["page_context_summary"] = "Steam-forward sizzle teaser for cravings."
    payload["scenes"][0]["objects"][1]["asset_label"] = "Sizzling hero plate"
    plan = CinematicReelPlan.model_validate(payload)
    report = validate_cinematic_plan_realism(
        plan,
        prompt_path_capabilities_aggregate=_static_aggregate(),
    )
    fb = report.as_dict()["failure_codes"]
    assert "prompt_path_impossible_sensory_claim" in fb

    repaired = repair_cinematic_plan_for_realism(plan, report)
    assert repaired.repaired is True
    assert "steam" not in repaired.plan.page_context_summary.lower()
    assert repaired.plan.scenes[0].objects[1].asset_label == "Sizzling hero plate"
