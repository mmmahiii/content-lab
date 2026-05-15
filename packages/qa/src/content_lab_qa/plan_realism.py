"""Realism QA for structured cinematic reel plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from content_lab_creative.planning_schema import CinematicReelPlan, TimelineObject

PlanRealismSeverity = Literal["warn", "fail"]


@dataclass(frozen=True, slots=True)
class PlanRealismFinding:
    code: str
    severity: PlanRealismSeverity
    message: str
    scene_id: str | None
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "scene_id": self.scene_id,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class PlanRealismReport:
    findings: tuple[PlanRealismFinding, ...]

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "fail" for finding in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "cinematic_plan_realism_qa_v1",
            "passed": self.passed,
            "findings": [finding.as_dict() for finding in self.findings],
            "failure_codes": [
                finding.code for finding in self.findings if finding.severity == "fail"
            ],
            "warning_codes": [
                finding.code for finding in self.findings if finding.severity == "warn"
            ],
        }


def validate_cinematic_plan_realism(plan: CinematicReelPlan) -> PlanRealismReport:
    """Return realism QA findings for a renderer-ready plan."""

    findings: list[PlanRealismFinding] = []
    for scene in plan.scenes:
        foreground = [
            item
            for item in scene.objects
            if item.role in {"hero_subject", "supporting_subject", "foreground_texture"}
        ]
        if len(foreground) > plan.realism_constraints.max_foreground_objects:
            findings.append(
                _finding(
                    "too_many_equal_priority_foreground_objects",
                    "fail",
                    "Too many foreground objects are active in one scene.",
                    scene.scene_id,
                    foreground_count=len(foreground),
                )
            )
        hero_count = sum(1 for item in foreground if item.role == "hero_subject")
        if hero_count > 1:
            findings.append(
                _finding(
                    "too_many_equal_priority_foreground_objects",
                    "fail",
                    "A scene should not have multiple simultaneous hero subjects.",
                    scene.scene_id,
                    hero_count=hero_count,
                )
            )
        if not any(item.role == scene.dominant_focal_role for item in scene.objects):
            findings.append(
                _finding(
                    "missing_dominant_subject",
                    "fail",
                    "Scene has no object matching the dominant focal role.",
                    scene.scene_id,
                )
            )
        _check_depth(scene.scene_id, scene.objects, findings=findings)
        _check_shadows(scene.scene_id, scene.objects, findings=findings)
        for caption in scene.captions:
            if not caption.safe_area_compliant or not caption.renderer_text_only:
                findings.append(
                    _finding(
                        "caption_not_renderer_safe",
                        "fail",
                        "Caption must be editable renderer text inside safe area.",
                        scene.scene_id,
                        caption_id=caption.caption_id,
                    )
                )
    if plan.provenance.realism_risk_score > 0.75:
        findings.append(
            _finding(
                "high_realism_risk_score",
                "warn",
                "Planner marked this composition as high realism risk.",
                None,
                realism_risk_score=plan.provenance.realism_risk_score,
            )
        )
    return PlanRealismReport(findings=tuple(findings))


def _check_depth(
    scene_id: str,
    objects: list[TimelineObject],
    *,
    findings: list[PlanRealismFinding],
) -> None:
    environment_depths = [item.z for item in objects if item.role == "environment_base"]
    foreground_depths = [
        item.z
        for item in objects
        if item.role in {"hero_subject", "supporting_subject", "foreground_texture"}
    ]
    if environment_depths and foreground_depths and max(environment_depths) >= min(foreground_depths):
        findings.append(
            _finding(
                "depth_order_inconsistent",
                "fail",
                "Foreground objects must be in front of environment/base layers.",
                scene_id,
            )
        )
    for item in objects:
        area = item.width_normalised * item.height_normalised * item.scale * item.scale
        if item.role in {"hero_subject", "supporting_subject"} and area < 0.015:
            findings.append(
                _finding(
                    "hero_subject_too_small",
                    "fail",
                    "Hero/supporting subject is too small to carry the visual hierarchy.",
                    scene_id,
                    object_id=item.object_id,
                    area=area,
                )
            )


def _check_shadows(
    scene_id: str,
    objects: list[TimelineObject],
    *,
    findings: list[PlanRealismFinding],
) -> None:
    for item in objects:
        if (
            item.role in {"atmospheric_layer", "motion_layer"}
            and item.shadow_spec.blur < 0.25
            and item.shadow_spec.enabled
            and item.shadow_spec.opacity > 0.2
        ):
            findings.append(
                _finding(
                    "atmospheric_layer_casts_hard_shadow",
                    "fail",
                    "Atmospheric layers should not cast hard visible shadows.",
                    scene_id,
                    object_id=item.object_id,
                )
            )
        if (
            item.role in {"hero_subject", "supporting_subject", "foreground_texture"}
            and (not item.shadow_spec.enabled or not item.shadow_spec.contact_shadow_required)
        ):
            findings.append(
                _finding(
                    "missing_contact_shadow",
                    "fail",
                    "Foreground objects require enabled contact shadows.",
                    scene_id,
                    object_id=item.object_id,
                )
            )


def _finding(
    code: str,
    severity: PlanRealismSeverity,
    message: str,
    scene_id: str | None,
    **details: Any,
) -> PlanRealismFinding:
    return PlanRealismFinding(
        code=code,
        severity=severity,
        message=message,
        scene_id=scene_id,
        details=details,
    )


__all__ = [
    "PlanRealismFinding",
    "PlanRealismReport",
    "PlanRealismSeverity",
    "validate_cinematic_plan_realism",
]
