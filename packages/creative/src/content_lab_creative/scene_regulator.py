"""Deterministic scene regulation checks for cinematic plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from content_lab_creative.planning_schema import CinematicReelPlan, ScenePlan

SceneRegulationSeverity = Literal["warn", "fail"]


@dataclass(frozen=True, slots=True)
class SceneRegulationFinding:
    code: str
    severity: SceneRegulationSeverity
    message: str
    scene_id: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "scene_id": self.scene_id,
        }


@dataclass(frozen=True, slots=True)
class SceneRegulationReport:
    findings: tuple[SceneRegulationFinding, ...]

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "fail" for finding in self.findings)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "scene_regulation_v1",
            "passed": self.passed,
            "findings": [finding.as_dict() for finding in self.findings],
            "failure_codes": [
                finding.code for finding in self.findings if finding.severity == "fail"
            ],
            "warning_codes": [
                finding.code for finding in self.findings if finding.severity == "warn"
            ],
        }


def regulate_cinematic_plan(plan: CinematicReelPlan) -> SceneRegulationReport:
    """Return deterministic scene coherence findings."""

    findings: list[SceneRegulationFinding] = []
    for scene in plan.scenes:
        _check_scene_focal_priority(scene, findings=findings)
        _check_object_reasons(scene, findings=findings)
        _check_depth_consistency(scene, findings=findings)
    return SceneRegulationReport(findings=tuple(findings))


def _check_scene_focal_priority(
    scene: ScenePlan,
    *,
    findings: list[SceneRegulationFinding],
) -> None:
    dominant_objects = [item for item in scene.objects if item.role == scene.dominant_focal_role]
    if not dominant_objects:
        findings.append(
            SceneRegulationFinding(
                code="missing_dominant_focal_object",
                severity="fail",
                message="Every scene must have one object carrying the dominant focal role.",
                scene_id=scene.scene_id,
            )
        )
        return
    high_priority_objects = [
        item for item in scene.objects if item.role in {"hero_subject", "narrative_payoff"}
    ]
    if len(high_priority_objects) > 2:
        findings.append(
            SceneRegulationFinding(
                code="too_many_high_priority_objects",
                severity="fail",
                message="Scene has too many high-priority foreground/payoff objects.",
                scene_id=scene.scene_id,
            )
        )


def _check_object_reasons(
    scene: ScenePlan,
    *,
    findings: list[SceneRegulationFinding],
) -> None:
    for item in scene.objects:
        if len(item.realism_reason.strip()) < 12:
            findings.append(
                SceneRegulationFinding(
                    code="object_missing_reason",
                    severity="fail",
                    message="Every object must explain why it exists in the scene.",
                    scene_id=scene.scene_id,
                )
            )


def _check_depth_consistency(
    scene: ScenePlan,
    *,
    findings: list[SceneRegulationFinding],
) -> None:
    for item in scene.objects:
        if item.role == "environment_base" and item.z > 0.35:
            findings.append(
                SceneRegulationFinding(
                    code="environment_too_foreground",
                    severity="fail",
                    message="Environment base objects must stay in background depth.",
                    scene_id=scene.scene_id,
                )
            )
        if item.role in {"hero_subject", "foreground_texture"} and item.z < 0.35:
            findings.append(
                SceneRegulationFinding(
                    code="foreground_too_far_back",
                    severity="fail",
                    message="Foreground/hero objects must not be placed in background depth.",
                    scene_id=scene.scene_id,
                )
            )


__all__ = [
    "SceneRegulationFinding",
    "SceneRegulationReport",
    "SceneRegulationSeverity",
    "regulate_cinematic_plan",
]
