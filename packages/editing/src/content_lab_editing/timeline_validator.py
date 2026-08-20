"""Validation helpers for cinematic reel timeline artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from content_lab_editing.reel_timeline_schema import ReelTimeline
from content_lab_editing.relationship_layout import enforce_relationship_layout
from content_lab_editing.support_surface_overlap import OverlapValidationContext

TimelineFindingSeverity = Literal["warn", "fail"]


@dataclass(frozen=True, slots=True)
class ReelTimelineFinding:
    code: str
    severity: TimelineFindingSeverity
    message: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class ReelTimelineValidationReport:
    findings: tuple[ReelTimelineFinding, ...]

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "fail" for finding in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reel_timeline_validation_v1",
            "passed": self.passed,
            "findings": [finding.as_dict() for finding in self.findings],
            "failure_codes": [
                finding.code for finding in self.findings if finding.severity == "fail"
            ],
        }


def validate_reel_timeline_artifact(
    payload: Mapping[str, Any],
    *,
    overlap_context: OverlapValidationContext | None = None,
) -> ReelTimelineValidationReport:
    """Validate a flattened reel timeline artifact before renderer handoff."""

    findings: list[ReelTimelineFinding] = []
    try:
        timeline = ReelTimeline.model_validate(dict(payload))
    except ValueError as exc:
        return ReelTimelineValidationReport(
            findings=(
                ReelTimelineFinding(
                    code="timeline_schema_invalid",
                    severity="fail",
                    message=str(exc),
                    details={},
                ),
            )
        )
    for item in timeline.objects:
        if item.x + (item.width_normalised * item.scale) / 2 > 1.08:
            findings.append(
                ReelTimelineFinding(
                    code="object_likely_out_of_frame",
                    severity="fail",
                    message="Object width and x placement likely exceed the right frame edge.",
                    details={"object_id": item.object_id},
                )
            )
        if item.y + (item.height_normalised * item.scale) / 2 > 1.08:
            findings.append(
                ReelTimelineFinding(
                    code="object_likely_out_of_frame",
                    severity="fail",
                    message="Object height and y placement likely exceed the bottom frame edge.",
                    details={"object_id": item.object_id},
                )
            )
    relationship_report = enforce_relationship_layout(
        timeline,
        overlap_context=overlap_context,
    )
    findings.extend(
        ReelTimelineFinding(
            code=finding.code,
            severity=finding.severity,
            message=finding.message,
            details=finding.details,
        )
        for finding in relationship_report.findings
    )
    for index, caption in enumerate(timeline.captions):
        if not bool(caption.get("safe_area_compliant", False)):
            findings.append(
                ReelTimelineFinding(
                    code="caption_safe_area_violation",
                    severity="fail",
                    message="Caption must be marked safe-area compliant.",
                    details={"index": index},
                )
            )
    return ReelTimelineValidationReport(findings=tuple(findings))


__all__ = [
    "ReelTimelineFinding",
    "ReelTimelineValidationReport",
    "TimelineFindingSeverity",
    "validate_reel_timeline_artifact",
]
