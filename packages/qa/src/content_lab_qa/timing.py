"""QA gate: overlay and scene timings vs final edit duration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from content_lab_core.types import QAVerdict
from content_lab_editing.timeline_validation import (
    DEFAULT_FRAME_TOLERANCE_SECONDS,
    DEFAULT_MIN_FINAL_CTA_DURATION_SECONDS,
    validate_timeline_against_final_duration,
)
from content_lab_qa.gate import QAResult


class TimelineTimingConstraints(BaseModel):
    """Thresholds for timeline duration QA."""

    model_config = ConfigDict(extra="forbid")

    min_final_cta_duration_seconds: float = Field(
        default=DEFAULT_MIN_FINAL_CTA_DURATION_SECONDS,
        ge=0.0,
        le=30.0,
    )
    frame_tolerance_seconds: float = Field(
        default=DEFAULT_FRAME_TOLERANCE_SECONDS,
        ge=0.0,
        le=1.0,
    )


TIMELINE_TIMING_GATE_NAME = "timeline_timing"


def evaluate_timeline_timing_qa(
    *,
    script: Mapping[str, Any],
    scene_plan: Mapping[str, Any] | None,
    editing: Mapping[str, Any],
    constraints: TimelineTimingConstraints | None = None,
) -> QAResult:
    """Block readiness when overlays/scenes fall outside final media duration or CTA is too short."""

    effective = constraints or TimelineTimingConstraints()
    duration_raw = editing.get("duration_seconds")
    if duration_raw is None:
        return QAResult(
            gate_name=TIMELINE_TIMING_GATE_NAME,
            verdict=QAVerdict.FAIL,
            message="Editing output is missing duration_seconds for timeline QA.",
            details={
                "findings": [
                    {
                        "code": "timeline_missing_final_duration",
                        "severity": "fail",
                        "message": "editing.duration_seconds must be set",
                        "details": {},
                    }
                ],
            },
        )

    try:
        final_duration = float(duration_raw)
    except (TypeError, ValueError):
        return QAResult(
            gate_name=TIMELINE_TIMING_GATE_NAME,
            verdict=QAVerdict.FAIL,
            message="Editing duration_seconds is not numeric.",
            details={"raw": duration_raw},
        )

    overlays = script.get("overlay_timeline")
    if not isinstance(overlays, list):
        overlays = []

    report = validate_timeline_against_final_duration(
        overlay_timeline=overlays,
        scene_plan=scene_plan,
        final_duration_seconds=final_duration,
        min_final_cta_duration_seconds=effective.min_final_cta_duration_seconds,
        frame_tolerance_seconds=effective.frame_tolerance_seconds,
    )

    if report.has_failures:
        verdict = QAVerdict.FAIL
    elif any(f.severity == "warn" for f in report.findings):
        verdict = QAVerdict.WARN
    else:
        verdict = QAVerdict.PASS

    summary = report.as_dict()
    fail_count = sum(1 for f in report.findings if f.severity == "fail")
    warn_count = sum(1 for f in report.findings if f.severity == "warn")
    if verdict == QAVerdict.FAIL:
        message = f"Timeline timing failed ({fail_count} blocking finding(s))."
    elif verdict == QAVerdict.WARN:
        message = f"Timeline timing passed with {warn_count} warning(s)."
    else:
        message = "Timeline timing passed."

    return QAResult(
        gate_name=TIMELINE_TIMING_GATE_NAME,
        verdict=verdict,
        message=message,
        details={
            "report": summary,
            "fail_count": fail_count,
            "warn_count": warn_count,
        },
    )


__all__ = [
    "TIMELINE_TIMING_GATE_NAME",
    "TimelineTimingConstraints",
    "evaluate_timeline_timing_qa",
]
