"""Perspective and surface-plane compatibility QA for cinematic plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from content_lab_creative.planning_schema import CinematicReelPlan, TimelineObject

PerspectiveSeverity = Literal["warn", "fail"]


@dataclass(frozen=True, slots=True)
class PerspectiveFinding:
    code: str
    severity: PerspectiveSeverity
    message: str
    scene_id: str | None
    suggested_fix: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "scene_id": self.scene_id,
            "suggested_fix": self.suggested_fix,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class PerspectiveReport:
    findings: tuple[PerspectiveFinding, ...]
    recommended_render_strategy: str | None
    realism_risk_delta: float

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "fail" for finding in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "perspective_compatibility_qa_v1",
            "passed": self.passed,
            "recommended_render_strategy": self.recommended_render_strategy,
            "realism_risk_delta": self.realism_risk_delta,
            "findings": [finding.as_dict() for finding in self.findings],
            "failure_codes": [
                finding.code for finding in self.findings if finding.severity == "fail"
            ],
            "warning_codes": [
                finding.code for finding in self.findings if finding.severity == "warn"
            ],
        }


def validate_perspective_compatibility(plan: CinematicReelPlan) -> PerspectiveReport:
    """Validate view angle, support plane, scale, and lighting compatibility."""

    findings: list[PerspectiveFinding] = []
    risk_delta = 0.0
    recommended: str | None = None
    scene_light_direction = _scene_light_direction(plan)
    realistic_mode = plan.render_strategy in {"realistic_single_scene", "realistic_sequence"}

    for scene in plan.scenes:
        objects_by_id = {item.object_id: item for item in scene.objects}
        unknown_view_count = sum(1 for item in scene.objects if item.view_angle == "unknown")
        if unknown_view_count >= max(2, len(scene.objects) // 2 + 1):
            risk_delta = max(risk_delta, 0.12)
            findings.append(
                _finding(
                    "unknown_perspective_metadata",
                    "warn",
                    "Several objects have unknown view_angle metadata.",
                    scene.scene_id,
                    "Add view_angle/surface_plane metadata or choose a safer graphic layout.",
                    unknown_count=unknown_view_count,
                )
            )
        for item in scene.objects:
            if item.role == "background_reveal" and item.z > 0.45:
                findings.append(
                    _finding(
                        "background_reveal_foreground_depth",
                        "fail",
                        "Background reveal is placed with foreground z-depth.",
                        scene.scene_id,
                        "Lower z-depth or change the role if it is meant to be a payoff object.",
                        object_id=item.object_id,
                        z=item.z,
                    )
                )
                recommended = recommended or "product_card_layout"
            if (
                item.lighting_direction != "unknown"
                and scene_light_direction != "unknown"
                and item.lighting_direction != scene_light_direction
                and "mixed" not in {item.lighting_direction, scene_light_direction}
            ):
                risk_delta = max(risk_delta, 0.1)
                findings.append(
                    _finding(
                        "lighting_direction_mismatch",
                        "warn",
                        "Object lighting direction conflicts with scene lighting.",
                        scene.scene_id,
                        "Reposition, relight in rendering, or downgrade to a graphic/card layout.",
                        object_id=item.object_id,
                        object_lighting=item.lighting_direction,
                        scene_lighting=scene_light_direction,
                    )
                )
            support = objects_by_id.get(item.support_object_id or "")
            if support is not None and item.spatial_relationship == "on_surface":
                severity: PerspectiveSeverity = "warn"
                code = "surface_plane_mismatch"
                if _severe_view_mismatch(support, item):
                    severity = "fail" if realistic_mode else "warn"
                    code = "view_angle_mismatch"
                    risk_delta = max(risk_delta, 0.3)
                    recommended = recommended or "product_card_layout"
                elif item.view_angle == "unknown" or support.view_angle == "unknown":
                    code = "unknown_supported_perspective"
                    risk_delta = max(risk_delta, 0.08)
                elif not _surface_plane_compatible(support, item):
                    risk_delta = max(risk_delta, 0.16)
                    recommended = recommended or "graphic_layout"
                else:
                    continue
                findings.append(
                    _finding(
                        code,
                        severity,
                        "Supported object perspective may not match its support surface.",
                        scene.scene_id,
                        "Use a matching angle/plane or downgrade to product_card_layout.",
                        object_id=item.object_id,
                        support_object_id=support.object_id,
                        object_view_angle=item.view_angle,
                        support_view_angle=support.view_angle,
                        object_surface_plane=item.surface_plane,
                        support_surface_plane=support.surface_plane,
                    )
                )
            if (
                item.role in {"supporting_subject", "foreground_texture"}
                and not item.support_object_id
                and item.surface_plane == "floating"
                and item.spatial_relationship != "atmospheric"
            ):
                findings.append(
                    _finding(
                        "floating_prop_without_support_plane",
                        "fail" if realistic_mode else "warn",
                        "Floating prop has no support plane.",
                        scene.scene_id,
                        "Attach it to a support, make it atmospheric, or use a graphic layout.",
                        object_id=item.object_id,
                    )
                )
                recommended = recommended or "graphic_layout"

    return PerspectiveReport(
        findings=tuple(findings),
        recommended_render_strategy=recommended,
        realism_risk_delta=risk_delta,
    )


def _scene_light_direction(plan: CinematicReelPlan) -> str:
    if "overhead" in plan.global_lighting_style.lower():
        return "overhead"
    if "front" in plan.global_lighting_style.lower():
        return "front"
    if "upper left" in plan.global_lighting_style.lower() or "left" in plan.global_lighting_style.lower():
        return "upper_left"
    if "upper right" in plan.global_lighting_style.lower() or "right" in plan.global_lighting_style.lower():
        return "upper_right"
    return "unknown"


def _severe_view_mismatch(support: TimelineObject, item: TimelineObject) -> bool:
    return support.view_angle in {"top_down", "overhead"} and item.view_angle == "front"


def _surface_plane_compatible(support: TimelineObject, item: TimelineObject) -> bool:
    if "unknown" in {support.surface_plane, item.surface_plane}:
        return True
    if support.surface_plane == "horizontal":
        return item.view_angle in {"top_down", "overhead", "three_quarter", "unknown"}
    if support.surface_plane == "vertical":
        return item.view_angle in {"front", "side", "three_quarter", "unknown"}
    return True


def _finding(
    code: str,
    severity: PerspectiveSeverity,
    message: str,
    scene_id: str | None,
    suggested_fix: str,
    **details: Any,
) -> PerspectiveFinding:
    return PerspectiveFinding(
        code=code,
        severity=severity,
        message=message,
        scene_id=scene_id,
        suggested_fix=suggested_fix,
        details=details,
    )


__all__ = [
    "PerspectiveFinding",
    "PerspectiveReport",
    "PerspectiveSeverity",
    "validate_perspective_compatibility",
]
