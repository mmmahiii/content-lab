"""Pre-render validation for text overlay timelines."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from content_lab_editing.overlays import (
    OverlayTimeline,
    OverlayTransitionSettings,
    list_pre_handoff_overlay_slots,
)

DEFAULT_FRAME_TOLERANCE_SECONDS = 1 / 24
DEFAULT_MIN_FINAL_CTA_DURATION_SECONDS = 0.75
TimelineFindingSeverity = Literal["warn", "fail"]


@dataclass(frozen=True, slots=True)
class OverlayCollision:
    """Two overlays whose effective drawtext windows overlap (non-stacking mode)."""

    overlay_id_a: str
    overlay_id_b: str
    text_a: str
    text_b: str
    overlap_start_seconds: float
    overlap_end_seconds: float
    reason: str


class OverlayTimelineCollisionError(RuntimeError):
    """Raised when a timeline would render overlapping primary text overlays."""

    def __init__(self, collisions: tuple[OverlayCollision, ...]) -> None:
        self.collisions = collisions
        super().__init__(_format_collision_message(collisions))


@dataclass(frozen=True, slots=True)
class TimelineValidationFinding:
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
class TimelineValidationReport:
    final_duration_seconds: float
    findings: tuple[TimelineValidationFinding, ...]

    @property
    def has_failures(self) -> bool:
        return any(f.severity == "fail" for f in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "final_duration_seconds": self.final_duration_seconds,
            "failed": self.has_failures,
            "findings": [f.as_dict() for f in self.findings],
        }


def _format_collision_message(collisions: tuple[OverlayCollision, ...]) -> str:
    parts: list[str] = ["text overlay timeline has overlapping primary cues:"]
    for hit in collisions:
        parts.append(
            f"  {hit.overlay_id_a!r} / {hit.overlay_id_b!r} "
            f"[{hit.overlap_start_seconds:.3f}s, {hit.overlap_end_seconds:.3f}s) — {hit.reason}"
        )
    return "\n".join(parts)


def _overlay_end_seconds(
    *,
    overlay_end: float | None,
    clip_duration_seconds: float | None,
) -> float | None:
    if overlay_end is not None:
        return float(overlay_end)
    if clip_duration_seconds is not None:
        return float(clip_duration_seconds)
    return None


def _half_open_overlap(
    a0: float,
    a1: float,
    b0: float,
    b1: float,
) -> tuple[float, float] | None:
    """Return overlap of [a0, a1) and [b0, b1) when it has positive width."""

    lo = max(a0, b0)
    hi = min(a1, b1)
    if lo < hi:
        return (lo, hi)
    return None


def _fade_summary(enter_ms: float | None, exit_ms: float | None) -> tuple[float, float]:
    e_in = 0.0 if enter_ms is None else float(enter_ms)
    e_out = 0.0 if exit_ms is None else float(exit_ms)
    return e_in, e_out


def detect_overlay_collisions(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
    allow_overlay_stack: bool = False,
    transition: OverlayTransitionSettings | None = None,
) -> tuple[OverlayCollision, ...]:
    """Return structural collisions for timelines that forbid stacked primary overlays.

    Uses the same timing normalization and fade merge as rendering, but **before**
    primary-track trimming. Overlap is measured on half-open ``[start, end)``
    drawtext enable windows; fade durations are included in the reported reason so
    authors can see the resolved ramp lengths that still share clock time with
    another cue.
    """

    if timeline is None:
        return ()
    if allow_overlay_stack:
        return ()
    if transition is not None and transition.allow_crossfade_overlap:
        return ()

    slots = list_pre_handoff_overlay_slots(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
        transition=transition,
    )
    if len(slots) < 2:
        return ()

    collisions: list[OverlayCollision] = []
    ends: list[float | None] = []
    for slot in slots:
        ends.append(
            _overlay_end_seconds(
                overlay_end=slot.overlay.end_seconds,
                clip_duration_seconds=clip_duration_seconds,
            )
        )

    for i in range(len(slots)):
        ov_a = slots[i].overlay
        end_a = ends[i]
        if end_a is None:
            continue
        start_a = ov_a.start_seconds
        for j in range(i + 1, len(slots)):
            ov_b = slots[j].overlay
            end_b = ends[j]
            if end_b is None:
                continue
            start_b = ov_b.start_seconds
            overlap = _half_open_overlap(start_a, end_a, start_b, end_b)
            if overlap is None:
                continue
            eia, xoa = _fade_summary(ov_a.enter_duration_ms, ov_a.exit_duration_ms)
            eib, xob = _fade_summary(ov_b.enter_duration_ms, ov_b.exit_duration_ms)
            reason = (
                "overlapping primary drawtext enable windows [start, end) with "
                f"resolved fades (enter_a={eia:g}ms exit_a={xoa:g}ms; "
                f"enter_b={eib:g}ms exit_b={xob:g}ms)"
            )
            collisions.append(
                OverlayCollision(
                    overlay_id_a=slots[i].stable_id,
                    overlay_id_b=slots[j].stable_id,
                    text_a=ov_a.text,
                    text_b=ov_b.text,
                    overlap_start_seconds=overlap[0],
                    overlap_end_seconds=overlap[1],
                    reason=reason,
                )
            )
    return tuple(collisions)


def validate_overlay_timeline_before_render(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
    allow_overlay_stack: bool = False,
    transition: OverlayTransitionSettings | None = None,
) -> None:
    """Raise :class:`OverlayTimelineCollisionError` when the timeline would collide."""

    hits = detect_overlay_collisions(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
        allow_overlay_stack=allow_overlay_stack,
        transition=transition,
    )
    if hits:
        raise OverlayTimelineCollisionError(hits)


def validate_timeline_against_final_duration(
    *,
    canonical_timeline: Mapping[str, Any] | None,
    final_duration_seconds: float,
    min_final_cta_duration_seconds: float = DEFAULT_MIN_FINAL_CTA_DURATION_SECONDS,
    frame_tolerance_seconds: float = DEFAULT_FRAME_TOLERANCE_SECONDS,
) -> TimelineValidationReport:
    findings: list[TimelineValidationFinding] = []
    final_duration = float(final_duration_seconds)
    tolerance = max(float(frame_tolerance_seconds), 0.0)

    overlays = (
        canonical_timeline.get("overlays") if isinstance(canonical_timeline, Mapping) else None
    )
    for index, raw in enumerate(overlays or ()):
        if not isinstance(raw, Mapping):
            continue
        start = _read_timing_float(raw, "start_seconds", "start") or 0.0
        end = _read_timing_float(raw, "end_seconds", "end")
        if end is None:
            findings.append(
                TimelineValidationFinding(
                    code="overlay_missing_required_end",
                    severity="fail",
                    message="Canonical timeline overlays must include explicit end_seconds.",
                    details={"index": index},
                )
            )
            continue
        if end > final_duration + tolerance:
            findings.append(
                TimelineValidationFinding(
                    code="overlay_exceeds_final_duration",
                    severity="fail",
                    message="Overlay cue extends beyond final edit duration.",
                    details={"index": index, "end_seconds": end},
                )
            )
        role = (
            str(raw.get("emphasis") or raw.get("overlay_role") or raw.get("role") or "")
            .strip()
            .lower()
        )
        if role in {"cta", "disclosure"} and end - start < min_final_cta_duration_seconds:
            findings.append(
                TimelineValidationFinding(
                    code="final_cta_too_short",
                    severity="fail",
                    message="Final CTA overlay is shorter than the configured minimum.",
                    details={
                        "index": index,
                        "duration_seconds": end - start,
                        "minimum_seconds": min_final_cta_duration_seconds,
                    },
                )
            )

    scenes = canonical_timeline.get("scenes") if isinstance(canonical_timeline, Mapping) else None
    if isinstance(scenes, list):
        for index, scene in enumerate(scenes):
            if not isinstance(scene, Mapping):
                continue
            end = _read_timing_float(scene, "end_seconds", "end")
            if end is not None and end > final_duration + tolerance:
                findings.append(
                    TimelineValidationFinding(
                        code="scene_exceeds_final_duration",
                        severity="fail",
                        message="Scene timing extends beyond final edit duration.",
                        details={"index": index, "end_seconds": end},
                    )
                )

    return TimelineValidationReport(
        final_duration_seconds=final_duration,
        findings=tuple(findings),
    )


def _read_timing_float(payload: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value: object = payload.get(key)
        if value in (None, "") or isinstance(value, bool):
            continue
        if isinstance(value, int | float | str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


__all__ = [
    "OverlayCollision",
    "OverlayTimelineCollisionError",
    "TimelineValidationFinding",
    "TimelineValidationReport",
    "DEFAULT_FRAME_TOLERANCE_SECONDS",
    "DEFAULT_MIN_FINAL_CTA_DURATION_SECONDS",
    "detect_overlay_collisions",
    "validate_timeline_against_final_duration",
    "validate_overlay_timeline_before_render",
]
