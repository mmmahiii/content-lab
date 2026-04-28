"""Validate overlay and scene-plan timings against final edit duration (phase-1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

# ~2 frames at 24 fps — accommodates fractional container duration vs timeline integers.
DEFAULT_FRAME_TOLERANCE_SECONDS = 2.0 / 24.0
DEFAULT_MIN_FINAL_CTA_DURATION_SECONDS = 0.75

Severity = Literal["fail", "warn"]


@dataclass(frozen=True, slots=True)
class TimelineValidationFinding:
    """Single timeline defect or warning."""

    code: str
    severity: Severity
    message: str
    details: dict[str, object]


@dataclass(frozen=True, slots=True)
class TimelineValidationReport:
    """Structured outcome of timeline validation."""

    findings: tuple[TimelineValidationFinding, ...]
    final_duration_seconds: float
    frame_tolerance_seconds: float

    @property
    def has_failures(self) -> bool:
        return any(f.severity == "fail" for f in self.findings)

    def as_dict(self) -> dict[str, object]:
        return {
            "final_duration_seconds": self.final_duration_seconds,
            "frame_tolerance_seconds": self.frame_tolerance_seconds,
            "findings": [
                {
                    "code": f.code,
                    "severity": f.severity,
                    "message": f.message,
                    "details": dict(f.details),
                }
                for f in self.findings
            ],
            "failed": self.has_failures,
        }


def validate_timeline_against_final_duration(
    *,
    overlay_timeline: Sequence[Mapping[str, object]] | None,
    scene_plan: Mapping[str, object] | None,
    final_duration_seconds: float,
    min_final_cta_duration_seconds: float = DEFAULT_MIN_FINAL_CTA_DURATION_SECONDS,
    frame_tolerance_seconds: float = DEFAULT_FRAME_TOLERANCE_SECONDS,
) -> TimelineValidationReport:
    """Check overlays/scenes against measured final media duration and CTA legibility rules."""

    if final_duration_seconds < 0:
        return TimelineValidationReport(
            findings=(
                TimelineValidationFinding(
                    code="timeline_invalid_final_duration",
                    severity="fail",
                    message="final_duration_seconds must not be negative",
                    details={"final_duration_seconds": final_duration_seconds},
                ),
            ),
            final_duration_seconds=final_duration_seconds,
            frame_tolerance_seconds=frame_tolerance_seconds,
        )

    tol = max(float(frame_tolerance_seconds), 0.0)
    final = float(final_duration_seconds)
    findings: list[TimelineValidationFinding] = []

    overlays = list(overlay_timeline) if overlay_timeline is not None else []
    for index, raw in enumerate(overlays):
        if not isinstance(raw, Mapping):
            findings.append(
                TimelineValidationFinding(
                    code="timeline_overlay_malformed",
                    severity="fail",
                    message=f"Overlay at index {index} is not an object",
                    details={"index": index},
                )
            )
            continue
        start = _read_seconds(raw.get("start_seconds", raw.get("start")))
        end = _read_seconds(raw.get("end_seconds", raw.get("end")))
        if start is None or end is None:
            findings.append(
                TimelineValidationFinding(
                    code="timeline_overlay_missing_bounds",
                    severity="fail",
                    message=f"Overlay at index {index} is missing numeric start/end seconds",
                    details={"index": index},
                )
            )
            continue

        if start < -tol:
            findings.append(
                TimelineValidationFinding(
                    code="timeline_overlay_starts_before_zero",
                    severity="fail",
                    message=f"Overlay at index {index} starts before t=0",
                    details={"index": index, "start_seconds": start},
                )
            )

        if end > final + tol:
            findings.append(
                TimelineValidationFinding(
                    code="timeline_overlay_ends_past_final",
                    severity="fail",
                    message=f"Overlay at index {index} ends after final media duration",
                    details={
                        "index": index,
                        "end_seconds": end,
                        "final_duration_seconds": final,
                        "tolerance_seconds": tol,
                    },
                )
            )

        if end <= start + tol:
            findings.append(
                TimelineValidationFinding(
                    code="timeline_overlay_non_positive_span",
                    severity="warn",
                    message=f"Overlay at index {index} has negligible or inverted duration",
                    details={"index": index, "start_seconds": start, "end_seconds": end},
                )
            )

    scenes = _scene_list(scene_plan)
    for index, raw in enumerate(scenes):
        if not isinstance(raw, Mapping):
            findings.append(
                TimelineValidationFinding(
                    code="timeline_scene_malformed",
                    severity="fail",
                    message=f"Scene at index {index} is not an object",
                    details={"index": index},
                )
            )
            continue
        start = _read_seconds(raw.get("start_seconds"))
        end = _read_seconds(raw.get("end_seconds"))
        scene_id = str(raw.get("scene_id", f"scene_{index}"))
        if start is None or end is None:
            findings.append(
                TimelineValidationFinding(
                    code="timeline_scene_missing_bounds",
                    severity="fail",
                    message=f"Scene {scene_id!r} is missing numeric start/end seconds",
                    details={"index": index, "scene_id": scene_id},
                )
            )
            continue
        if start < -tol:
            findings.append(
                TimelineValidationFinding(
                    code="timeline_scene_starts_before_zero",
                    severity="fail",
                    message=f"Scene {scene_id!r} starts before t=0",
                    details={"scene_id": scene_id, "start_seconds": start},
                )
            )
        if end > final + tol:
            findings.append(
                TimelineValidationFinding(
                    code="timeline_scene_ends_past_final",
                    severity="fail",
                    message=f"Scene {scene_id!r} ends after final media duration",
                    details={
                        "scene_id": scene_id,
                        "end_seconds": end,
                        "final_duration_seconds": final,
                        "tolerance_seconds": tol,
                    },
                )
            )

    _append_final_cta_findings(
        overlays,
        final_seconds=final,
        tolerance_seconds=tol,
        min_cta_seconds=min_final_cta_duration_seconds,
        findings=findings,
    )

    return TimelineValidationReport(
        findings=tuple(findings),
        final_duration_seconds=final,
        frame_tolerance_seconds=tol,
    )


def _append_final_cta_findings(
    overlays: list[Mapping[str, object]],
    *,
    final_seconds: float,
    tolerance_seconds: float,
    min_cta_seconds: float,
    findings: list[TimelineValidationFinding],
) -> None:
    """Ensure the last CTA/disclosure overlay is on-screen long enough within the final cut."""

    emphasis_raw = ("cta", "disclosure")
    candidates: list[tuple[int, float, float, str]] = []
    for index, raw in enumerate(overlays):
        if not isinstance(raw, Mapping):
            continue
        emph = str(raw.get("emphasis", "") or "").strip().lower()
        if emph not in emphasis_raw:
            continue
        start = _read_seconds(raw.get("start_seconds", raw.get("start")))
        end = _read_seconds(raw.get("end_seconds", raw.get("end")))
        if start is None or end is None:
            continue
        candidates.append((index, float(start), float(end), emph))

    if not candidates:
        return

    # Final CTA card: prefer latest start among CTA/disclosure overlays (typically the close beat).
    _, start, end, emphasis = max(candidates, key=lambda item: (item[1], item[2]))
    vis_start = max(0.0, start)
    vis_end = min(end, final_seconds + tolerance_seconds)
    visible = max(0.0, vis_end - vis_start)
    if visible + tolerance_seconds < min_cta_seconds:
        findings.append(
            TimelineValidationFinding(
                code="timeline_final_cta_too_short",
                severity="fail",
                message="Final CTA/disclosure overlay visible span is shorter than the minimum",
                details={
                    "emphasis": emphasis,
                    "start_seconds": start,
                    "end_seconds": end,
                    "visible_seconds": visible,
                    "min_seconds": min_cta_seconds,
                    "final_duration_seconds": final_seconds,
                    "tolerance_seconds": tolerance_seconds,
                },
            )
        )


def _scene_list(scene_plan: Mapping[str, object] | None) -> list[Mapping[str, object]]:
    if scene_plan is None or not isinstance(scene_plan, Mapping):
        return []
    raw = scene_plan.get("scenes")
    if not isinstance(raw, list):
        return []
    return [s for s in raw if isinstance(s, Mapping)]


def _read_seconds(value: object) -> float | None:
    if value is None or value is False or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


__all__ = [
    "DEFAULT_FRAME_TOLERANCE_SECONDS",
    "DEFAULT_MIN_FINAL_CTA_DURATION_SECONDS",
    "TimelineValidationFinding",
    "TimelineValidationReport",
    "validate_timeline_against_final_duration",
]
