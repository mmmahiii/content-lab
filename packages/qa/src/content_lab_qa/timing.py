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
    audio_drift_tolerance_seconds: float = Field(default=0.25, ge=0.0, le=2.0)


TIMELINE_TIMING_GATE_NAME = "timeline_timing"
MEDIA_SYNC_GATE_NAME = "media_sync"


def evaluate_timeline_timing_qa(
    *,
    script: Mapping[str, Any],
    scene_plan: Mapping[str, Any] | None,
    editing: Mapping[str, Any],
    constraints: TimelineTimingConstraints | None = None,
) -> QAResult:
    """Block readiness when canonical timeline and final edit timing diverge."""

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

    timeline_payload = editing.get("timeline")
    if not isinstance(timeline_payload, Mapping):
        return QAResult(
            gate_name=TIMELINE_TIMING_GATE_NAME,
            verdict=QAVerdict.FAIL,
            message="Editing output is missing canonical timeline payload.",
            details={
                "findings": [
                    {
                        "code": "canonical_timeline_missing",
                        "severity": "fail",
                        "message": "editing.timeline must be present for strict MED-001 validation.",
                        "details": {},
                    }
                ],
            },
        )

    timeline_duration_f = _as_float(timeline_payload.get("duration_seconds"))
    if timeline_duration_f is None:
        return QAResult(
            gate_name=TIMELINE_TIMING_GATE_NAME,
            verdict=QAVerdict.FAIL,
            message="Canonical timeline duration_seconds is missing or invalid.",
            details={"raw": timeline_payload.get("duration_seconds")},
        )

    duration_delta = abs(timeline_duration_f - final_duration)
    if duration_delta > effective.frame_tolerance_seconds:
        return QAResult(
            gate_name=TIMELINE_TIMING_GATE_NAME,
            verdict=QAVerdict.FAIL,
            message="Final edit duration does not match canonical timeline duration.",
            details={
                "timeline_duration_seconds": timeline_duration_f,
                "final_duration_seconds": final_duration,
                "delta_seconds": duration_delta,
                "tolerance_seconds": effective.frame_tolerance_seconds,
            },
        )

    report = validate_timeline_against_final_duration(
        canonical_timeline=timeline_payload,
        final_duration_seconds=final_duration,
        min_final_cta_duration_seconds=effective.min_final_cta_duration_seconds,
        frame_tolerance_seconds=effective.frame_tolerance_seconds,
    )

    extra_findings: list[dict[str, Any]] = []
    cover_ts = editing.get("cover_frame_timestamp_seconds")
    if cover_ts is None:
        extra_findings.append(
            {
                "code": "cover_timestamp_missing",
                "severity": "fail",
                "message": "Editing output missing cover_frame_timestamp_seconds.",
                "details": {},
            }
        )
    else:
        try:
            cover_ts_f = float(cover_ts)
            if cover_ts_f < 0 or cover_ts_f > final_duration + effective.frame_tolerance_seconds:
                extra_findings.append(
                    {
                        "code": "cover_timestamp_out_of_range",
                        "severity": "fail",
                        "message": "Cover frame timestamp is outside canonical timeline duration.",
                        "details": {"cover_frame_timestamp_seconds": cover_ts_f},
                    }
                )
        except (TypeError, ValueError):
            extra_findings.append(
                {
                    "code": "cover_timestamp_invalid",
                    "severity": "fail",
                    "message": "Cover frame timestamp is not numeric.",
                    "details": {"raw": cover_ts},
                }
            )

    has_report_failures = report.has_failures
    has_extra_failures = any(item["severity"] == "fail" for item in extra_findings)
    if has_report_failures or has_extra_failures:
        verdict = QAVerdict.FAIL
    elif any(f.severity == "warn" for f in report.findings):
        verdict = QAVerdict.WARN
    else:
        verdict = QAVerdict.PASS

    summary = report.as_dict()
    if extra_findings:
        summary["findings"] = [*summary.get("findings", []), *extra_findings]
    fail_count = sum(1 for f in summary.get("findings", []) if f.get("severity") == "fail")
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


def evaluate_media_sync_qa(
    *,
    editing: Mapping[str, Any],
    constraints: TimelineTimingConstraints | None = None,
) -> QAResult:
    """Hard-block readiness when timeline/media sync checks fail."""

    effective = constraints or TimelineTimingConstraints()
    findings: list[dict[str, Any]] = []

    final_duration = _as_float(editing.get("duration_seconds"))
    if final_duration is None:
        return QAResult(
            gate_name=MEDIA_SYNC_GATE_NAME,
            verdict=QAVerdict.FAIL,
            message="Editing output is missing duration_seconds for media sync QA.",
            details={"findings": [{"code": "final_duration_missing", "severity": "fail"}]},
        )

    timeline_payload = editing.get("timeline")
    if not isinstance(timeline_payload, Mapping):
        return QAResult(
            gate_name=MEDIA_SYNC_GATE_NAME,
            verdict=QAVerdict.FAIL,
            message="Editing output is missing canonical timeline for media sync QA.",
            details={"findings": [{"code": "timeline_missing", "severity": "fail"}]},
        )

    timeline_duration = _as_float(timeline_payload.get("duration_seconds"))
    if timeline_duration is None:
        findings.append(
            {
                "code": "video_duration_mismatch",
                "severity": "fail",
                "message": "timeline.duration_seconds is missing",
            }
        )
    elif abs(timeline_duration - final_duration) > effective.frame_tolerance_seconds:
        findings.append(
            {
                "code": "video_duration_mismatch",
                "severity": "fail",
                "message": "Final video duration mismatches canonical timeline duration.",
                "details": {
                    "timeline_duration_seconds": timeline_duration,
                    "final_duration_seconds": final_duration,
                    "tolerance_seconds": effective.frame_tolerance_seconds,
                },
            }
        )

    scenes = timeline_payload.get("scenes")
    if isinstance(scenes, list):
        for index, scene in enumerate(scenes):
            if not isinstance(scene, Mapping):
                continue
            scene_end = _as_float(scene.get("end_seconds"))
            if (
                scene_end is not None
                and scene_end > final_duration + effective.frame_tolerance_seconds
            ):
                findings.append(
                    {
                        "code": "scene_plan_exceeds_actual_media",
                        "severity": "fail",
                        "message": "Scene plan extends beyond actual media duration.",
                        "details": {"index": index, "end_seconds": scene_end},
                    }
                )

    overlays = timeline_payload.get("overlays")
    if isinstance(overlays, list):
        for index, overlay in enumerate(overlays):
            if not isinstance(overlay, Mapping):
                continue
            end_seconds = _as_float(overlay.get("end_seconds"))
            if (
                end_seconds is not None
                and end_seconds > final_duration + effective.frame_tolerance_seconds
            ):
                findings.append(
                    {
                        "code": "overlay_exceeds_final_duration",
                        "severity": "fail",
                        "message": "Overlay exceeds final video duration.",
                        "details": {"index": index, "end_seconds": end_seconds},
                    }
                )

    cover_ts = _as_float(editing.get("cover_frame_timestamp_seconds"))
    if cover_ts is None:
        findings.append(
            {
                "code": "cover_timestamp_exceeds_duration",
                "severity": "fail",
                "message": "cover_frame_timestamp_seconds is missing or invalid.",
            }
        )
    elif cover_ts > final_duration + effective.frame_tolerance_seconds:
        findings.append(
            {
                "code": "cover_timestamp_exceeds_duration",
                "severity": "fail",
                "message": "Cover timestamp exceeds final duration.",
                "details": {"cover_frame_timestamp_seconds": cover_ts},
            }
        )

    audio_tracks = timeline_payload.get("audio_tracks")
    if isinstance(audio_tracks, list):
        max_audio_end = 0.0
        for track in audio_tracks:
            if not isinstance(track, Mapping):
                continue
            track_end = _as_float(track.get("end_seconds"))
            if track_end is not None:
                max_audio_end = max(max_audio_end, track_end)
        if abs(max_audio_end - final_duration) > effective.frame_tolerance_seconds:
            findings.append(
                {
                    "code": "audio_duration_mismatch",
                    "severity": "fail",
                    "message": "Audio timeline duration mismatches final video duration.",
                    "details": {
                        "audio_end_seconds": max_audio_end,
                        "final_duration_seconds": final_duration,
                        "tolerance_seconds": effective.frame_tolerance_seconds,
                    },
                }
            )

    trace = editing.get("timeline_render_trace")
    if isinstance(trace, Mapping):
        duration_checks = trace.get("duration_mismatch_checks")
        if isinstance(duration_checks, Mapping):
            mismatches = duration_checks.get("mismatches")
            if isinstance(mismatches, list) and mismatches:
                findings.append(
                    {
                        "code": "video_duration_mismatch",
                        "severity": "fail",
                        "message": "Duration mismatch checks reported timeline/media divergence.",
                        "details": {"mismatches": mismatches},
                    }
                )
        audio_timings = trace.get("audio_timings")
        if isinstance(audio_timings, list):
            max_audio_end_trace = 0.0
            for track in audio_timings:
                if not isinstance(track, Mapping):
                    continue
                track_end = _as_float(track.get("end_seconds"))
                if track_end is not None:
                    max_audio_end_trace = max(max_audio_end_trace, track_end)
            drift = abs(max_audio_end_trace - final_duration)
            if drift > effective.audio_drift_tolerance_seconds:
                findings.append(
                    {
                        "code": "audio_drift_exceeds_tolerance",
                        "severity": "fail",
                        "message": "Audio drift exceeds tolerance.",
                        "details": {
                            "audio_end_seconds": max_audio_end_trace,
                            "final_duration_seconds": final_duration,
                            "drift_seconds": drift,
                            "tolerance_seconds": effective.audio_drift_tolerance_seconds,
                        },
                    }
                )

    if findings:
        return QAResult(
            gate_name=MEDIA_SYNC_GATE_NAME,
            verdict=QAVerdict.FAIL,
            message=f"Media sync failed ({len(findings)} blocking finding(s)).",
            details={"findings": findings},
        )
    return QAResult(
        gate_name=MEDIA_SYNC_GATE_NAME,
        verdict=QAVerdict.PASS,
        message="Media sync checks passed.",
        details={"findings": []},
    )


def _as_float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "TIMELINE_TIMING_GATE_NAME",
    "MEDIA_SYNC_GATE_NAME",
    "TimelineTimingConstraints",
    "evaluate_media_sync_qa",
    "evaluate_timeline_timing_qa",
]
