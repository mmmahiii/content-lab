"""Validator-driven repair prompts for pasted cinematic reel plans."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from content_lab_creative.planning_schema import CinematicReelPlan
from content_lab_creative.scene_regulator import SceneRegulationFinding, regulate_cinematic_plan
from content_lab_creative.single_prompt_reel_planner import (
    PLANNING_PROMPT_VERSION,
    SinglePromptPlannerInput,
    attach_plan_hash,
    compute_plan_hash,
    normalize_pasted_plan_payload,
    parse_pasted_json,
)
from content_lab_creative.single_prompt_reel_planner import (
    _validate_against_prompt_request as _plan_contract_validate,
)

REPAIR_PROMPT_VERSION = "cinematic_plan_repair_prompt_v1"
RECOMMENDED_REPAIR_MODEL = "gpt-5-mini"

PlannerValidationSeverity = Literal["fail", "warn"]


_REGULATION_SUGGESTED_FIXES: dict[str, str] = {
    "missing_dominant_focal_object": (
        "Ensure dominant_focal_role matches an object role present in each scene's objects[].role."
    ),
    "too_many_high_priority_objects": (
        "Reject weaker hero/narrative_payoff duplicates via provenance.rejected_assets or downgrade layout."
    ),
    "object_missing_reason": (
        "Expand realism_reason on each timeline object (minimum substantive explanation)."
    ),
    "environment_too_foreground": (
        "Pull environment_base z toward background depth or downgrade render_strategy."
    ),
    "foreground_too_far_back": (
        "Raise hero_subject / foreground_texture z above 0.35 or shift to product_card_layout."
    ),
}


@dataclass(frozen=True, slots=True)
class PlannerValidationFinding:
    code: str
    severity: PlannerValidationSeverity
    message: str
    suggested_fix: str = ""
    scene_id: str | None = None
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "scene_id": self.scene_id,
            "details": dict(self.details or {}),
        }


@dataclass(frozen=True, slots=True)
class PlannerValidationReport:
    passed: bool
    findings: tuple[PlannerValidationFinding, ...]
    normalization_repairs: tuple[dict[str, Any], ...] = ()

    def failure_codes(self) -> list[str]:
        return [f.code for f in self.findings if f.severity == "fail"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "planner_validation_report_v1",
            "repair_prompt_version": REPAIR_PROMPT_VERSION,
            "passed": self.passed,
            "failure_codes": self.failure_codes(),
            "findings": [f.as_dict() for f in self.findings],
            "normalization_repairs": list(self.normalization_repairs),
        }


def _finding(
    code: str,
    severity: PlannerValidationSeverity,
    message: str,
    *,
    suggested_fix: str = "",
    scene_id: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> PlannerValidationFinding:
    return PlannerValidationFinding(
        code=code,
        severity=severity,
        message=message,
        suggested_fix=suggested_fix,
        scene_id=scene_id,
        details=dict(details) if details else None,
    )


def _contract_fix_hint(exc_message: str) -> str:
    lowered = exc_message.lower()
    if "missing pinned" in lowered:
        return "Include every pinned_prompt_paths entry inside selected_prompt_paths."
    if "banned paths" in lowered:
        return "Remove banned paths from selected_prompt_paths."
    if "prompt paths are not eligible" in lowered:
        return (
            "Swap disallowed sensory/process paths for eligible paths from planner "
            "allowed_prompt_paths or downgrade narrative tone."
        )
    if "provenance.selected_asset_ids" in lowered:
        return (
            "Set provenance.selected_asset_ids exactly equal to planner selected_asset_ids "
            "(same multiset). Never invent IDs."
        )
    if "input_page_context_hash" in lowered:
        return "Copy provenance.input_page_context_hash verbatim from planner input payload."
    if "planning_prompt_version" in lowered:
        return f"Set provenance.planning_prompt_version to {PLANNING_PROMPT_VERSION}."
    if "pan-shaped cutout" in lowered:
        return "Keep only one pan-shaped foreground asset per scene; reject duplicates."
    return "Re-read planner contract checklist against planner JSON payload."


def _findings_from_regulation(items: Sequence[SceneRegulationFinding]) -> list[PlannerValidationFinding]:
    results: list[PlannerValidationFinding] = []
    for item in items:
        fix = _REGULATION_SUGGESTED_FIXES.get(item.code, "Adjust scene composition per regulation message.")
        results.append(
            _finding(
                item.code,
                item.severity,
                item.message,
                suggested_fix=fix,
                scene_id=item.scene_id,
                details={"source": "scene_regulator"},
            )
        )
    return results


def analyze_cinematic_plan_validation(
    raw_plan_json: str | Mapping[str, Any],
    *,
    planner_input: SinglePromptPlannerInput,
) -> PlannerValidationReport:
    """Run deterministic validators without raising; aggregate structured failures for repair prompts."""

    findings: list[PlannerValidationFinding] = []
    repairs: tuple[dict[str, Any], ...] = ()

    raw_payload: Mapping[str, Any]
    try:
        raw_payload = (
            parse_pasted_json(raw_plan_json) if isinstance(raw_plan_json, str) else dict(raw_plan_json)
        )
    except (json.JSONDecodeError, ValueError) as exc:
        findings.append(
            _finding(
                "invalid_json",
                "fail",
                str(exc),
                suggested_fix="Return syntactically valid JSON matching CinematicReelPlan.",
                details={"error_type": type(exc).__name__},
            )
        )
        return PlannerValidationReport(passed=False, findings=tuple(findings))

    normalized, repair_list = normalize_pasted_plan_payload(
        raw_payload,
        selected_asset_ids=planner_input.selected_asset_ids,
    )
    repairs = tuple(repair_list)

    try:
        plan = CinematicReelPlan.model_validate(normalized)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(segment) for segment in err.get("loc", ()))
            msg = err.get("msg", "validation error")
            findings.append(
                _finding(
                    "schema_validation",
                    "fail",
                    f"{loc}: {msg}",
                    suggested_fix="Bring JSON back into schema compliance before retrying regulation.",
                    details={"pydantic_error": err},
                )
            )
        return PlannerValidationReport(
            passed=False,
            findings=tuple(findings),
            normalization_repairs=repairs,
        )

    try:
        _plan_contract_validate(plan, planner_input=planner_input)
    except ValueError as exc:
        findings.append(
            _finding(
                "prompt_contract_violation",
                "fail",
                str(exc),
                suggested_fix=_contract_fix_hint(str(exc)),
                details={"exception_type": type(exc).__name__},
            )
        )
        return PlannerValidationReport(
            passed=False,
            findings=tuple(findings),
            normalization_repairs=repairs,
        )

    plan_hash = compute_plan_hash(plan)
    hashed_plan = attach_plan_hash(plan, plan_hash)
    regulation = regulate_cinematic_plan(hashed_plan)
    findings.extend(_findings_from_regulation(regulation.findings))

    failed = any(item.severity == "fail" for item in findings)
    return PlannerValidationReport(
        passed=not failed,
        findings=tuple(findings),
        normalization_repairs=repairs,
    )


def build_repair_prompt(
    *,
    planner_input: SinglePromptPlannerInput,
    invalid_plan_json_text: str,
    validation_report: PlannerValidationReport,
    recommended_model: str = RECOMMENDED_REPAIR_MODEL,
) -> str:
    """Focused ChatGPT prompt that converts validator failures into corrected JSON."""

    planner_snapshot = json.dumps(
        {
            "planning_prompt_version": PLANNING_PROMPT_VERSION,
            "repair_prompt_version": REPAIR_PROMPT_VERSION,
            "page_context": planner_input.page_context,
            "selected_asset_ids": planner_input.selected_asset_ids,
            "content_goal": planner_input.content_goal,
            "pinned_prompt_paths": planner_input.pinned_prompt_paths,
            "banned_prompt_paths": planner_input.banned_prompt_paths,
            "duration_target_seconds": planner_input.duration_target_seconds,
            "brand_persona_constraints": planner_input.brand_persona_constraints,
            "platform_constraints": planner_input.platform_constraints,
            "input_page_context_hash": planner_input.input_page_context_hash,
        },
        indent=2,
        sort_keys=True,
    )
    eligibility_payload = json.dumps(
        {
            "selected_asset_ids_exact": planner_input.selected_asset_ids,
            "must_remain_exact": True,
        },
        indent=2,
    )
    failures_json = json.dumps(validation_report.as_dict(), indent=2, sort_keys=True)

    codes_line = ", ".join(validation_report.failure_codes()) or "(none)"

    return f"""You are repairing a rejected Content Lab CinematicReelPlan JSON.

Use model: {recommended_model}.
Return ONLY corrected JSON (no Markdown fences, no commentary).

Repair contract version: {REPAIR_PROMPT_VERSION}.
Planner contract version expected in provenance: {PLANNING_PROMPT_VERSION}.

Immutable identifiers — HARD RULES:
- Do NOT invent asset_ids or registry identifiers. Every asset_id must appear in planner selected_asset_ids.
- provenance.selected_asset_ids MUST remain exactly this ordered list (same values, same length): {json.dumps(planner_input.selected_asset_ids)}
- Do NOT introduce placeholder visuals pretending to be new uploads; reject clutter via provenance.rejected_assets instead.
- Downgrade render_strategy (product_card_layout / graphic_layout / low_res_texture_backdrop) instead of hallucinating realism.

Repair tactics priority:
1. Fix schema/regulation violations using ONLY existing assets or justified rejections.
2. Trim duplicate-role clutter — reject weaker duplicates with explicit reasons.
3. Refresh spatial_relationship / support_object_id / realism_reason fields where flagged.
4. If spatial realism stays impossible with allowed assets, downgrade render_strategy with frank render_notes.
5. For placement failures, change x/y/z/scale/opacity/relationship fields, or reject the object in provenance.rejected_assets.
6. For background_reveal failures, keep the object behind the hero, below max_overlap_ratio, and in declared rear/background regions.
7. Do not delete an object silently: removed objects must appear in provenance.rejected_assets with a specific reason.

Background_reveal numeric repair rules:
- Set background_reveal z <= 0.45 and lower than the hero_subject z in the same scene.
- Move it to upper_left, upper_right, background_left, background_right, rear, or side.
- Keep hero overlap <= max_overlap_ratio; if uncertain, set max_overlap_ratio to 0.10 and reduce scale/opacity.
- Do not leave preferred_screen_regions as foreground, lower_third, center, or full_frame for background_reveal.
- If those constraints cannot be met cleanly, remove the object from scenes[].objects and list it in provenance.rejected_assets with a reason.

Validator failure summary:
Failure codes: {codes_line}

Full validator payload:
{failures_json}

Original planner constraints snapshot:
{planner_snapshot}

Asset ID preservation checklist:
{eligibility_payload}

Invalid candidate JSON (must be repaired):
{invalid_plan_json_text.strip()}

Return exactly one JSON object matching CinematicReelPlan that passes deterministic validators.
"""


__all__ = [
    "REPAIR_PROMPT_VERSION",
    "RECOMMENDED_REPAIR_MODEL",
    "PlannerValidationFinding",
    "PlannerValidationReport",
    "analyze_cinematic_plan_validation",
    "build_repair_prompt",
]
