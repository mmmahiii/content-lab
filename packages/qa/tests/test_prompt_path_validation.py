from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from content_lab_creative.planning_schema import CinematicReelPlan
from content_lab_qa.plan_realism import validate_cinematic_plan_realism
from content_lab_qa.prompt_path_validation import validate_prompt_path_motion_claims

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


def test_motion_claim_fails_when_language_implies_chopping_for_static_bank() -> None:
    payload = copy.deepcopy(_valid_plan_dict())
    payload["narrative_arc"] = {
        "hook": "Chopping garnish neatly before serving.",
        "development": "Hold one calm tabletop framing beat.",
        "reveal_payoff": "Clean readable hero silhouette.",
        "closing_retention_loop": "Zoom-ready closing frame.",
    }
    payload["scenes"][0]["purpose"] = "Single tabletop hero beat without motion claims."
    payload["scenes"][0]["captions"][0]["text"] = "Why cooks prefer this jar."
    payload["caption_strategy"] = "Minimal captions."
    payload["audio_strategy"] = "Silent reel."
    payload["audio_plan"] = {"layers": [], "sync_points": [], "sensory_moments": []}

    plan = CinematicReelPlan.model_validate(payload)
    findings = validate_prompt_path_motion_claims(plan, aggregate=_static_aggregate())
    codes = {finding.code for finding in findings}
    assert "prompt_path_impossible_physical_motion_claim" in codes


def test_motion_claim_fails_on_steam_language_without_sensory_evidence() -> None:
    payload = copy.deepcopy(_valid_plan_dict())
    payload["narrative_arc"] = {
        "hook": "Steam cues appetite before captions.",
        "development": "Hold tabletop framing steady.",
        "reveal_payoff": "Readable hero label-forward payoff.",
        "closing_retention_loop": "Loop-safe closing frame.",
    }
    payload["audio_plan"] = {"layers": [], "sync_points": [], "sensory_moments": []}
    payload["audio_strategy"] = "Silent reel."

    plan = CinematicReelPlan.model_validate(payload)
    findings = validate_prompt_path_motion_claims(plan, aggregate=_static_aggregate())
    codes = {finding.code for finding in findings}
    assert "prompt_path_impossible_sensory_claim" in codes


def test_safe_static_product_card_language_passes_motion_claim_gate() -> None:
    payload = copy.deepcopy(_valid_plan_dict())
    payload["render_strategy"] = "product_card_layout"
    payload["selected_prompt_paths"] = ["cinematic_closeup", "object_story", "educational_overlay"]
    payload["provenance"]["selected_prompt_paths"] = payload["selected_prompt_paths"]
    payload["narrative_arc"] = {
        "hook": "Glass pantry styling cue.",
        "development": "Hold framing steady with subtle camera push.",
        "reveal_payoff": "Typography-forward payoff.",
        "closing_retention_loop": "Loop-safe closing frame.",
    }
    payload["scenes"][0]["purpose"] = "Clean tabletop hero framing."
    payload["scenes"][0]["emotional_intent"] = "Premium clarity without motion tricks."
    payload["scenes"][0]["captions"][0]["text"] = "Why cooks prefer this jar."
    payload["caption_strategy"] = "Minimal captions."
    payload["audio_strategy"] = "Silent reel."
    payload["audio_plan"] = {"layers": [], "sync_points": [], "sensory_moments": []}

    plan = CinematicReelPlan.model_validate(payload)
    findings = validate_prompt_path_motion_claims(plan, aggregate=_static_aggregate())
    assert findings == []


def test_plan_realism_merges_motion_claim_failures() -> None:
    payload = copy.deepcopy(_valid_plan_dict())
    payload["narrative_arc"]["hook"] = "Pouring glaze evenly across the hero."
    payload["audio_plan"] = {"layers": [], "sync_points": [], "sensory_moments": []}

    plan = CinematicReelPlan.model_validate(payload)
    report = validate_cinematic_plan_realism(
        plan,
        prompt_path_capabilities_aggregate=_static_aggregate(),
    )
    assert not report.passed
    assert "prompt_path_impossible_physical_motion_claim" in report.as_dict()["failure_codes"]
