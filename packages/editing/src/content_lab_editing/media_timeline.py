"""Canonical media timeline trace and validation helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

AUDIO_VIDEO_SYNC_TOLERANCE_SECONDS = 0.35
EDITING_DURATION_TOLERANCE_SECONDS = 0.35
CREATIVE_DURATION_TOLERANCE_SECONDS = 0.75
TIMING_BOUNDS_TOLERANCE_SECONDS = 0.35
SOURCE_DURATION_TOLERANCE_SECONDS = 0.35


def build_timeline_render_trace(
    *,
    canonical_timeline: Mapping[str, Any],
    final_video_duration_seconds: float,
    final_video_width: int | None,
    final_video_height: int | None,
    final_video_fps: float | None = None,
    final_video_path_or_uri: str | None = None,
    final_video_has_video_stream: bool = True,
    final_video_has_audio_stream: bool,
    final_audio_duration_seconds: float | None,
    final_video_codec: str | None = None,
    final_audio_codec: str | None = None,
    source_asset_duration_seconds: float | None,
    source_path_or_uri: str | None = None,
    creative_duration_seconds: float | None = None,
    editing_duration_seconds: float | None = None,
    cover_timestamp_seconds: float | None,
    audio_padded: bool = False,
    audio_trimmed: bool = False,
    source_padded: bool = False,
    source_looped: bool = False,
    source_trimmed: bool = False,
) -> dict[str, Any]:
    """Build the durable media timeline trace stored with every reel package."""

    timeline_duration = _as_float(canonical_timeline.get("duration_seconds"))
    creative_duration = (
        timeline_duration if creative_duration_seconds is None else float(creative_duration_seconds)
    )
    editing_duration = (
        timeline_duration if editing_duration_seconds is None else float(editing_duration_seconds)
    )
    final_duration = float(final_video_duration_seconds)
    audio_duration = (
        None if final_audio_duration_seconds is None else float(final_audio_duration_seconds)
    )
    source_duration = (
        None if source_asset_duration_seconds is None else float(source_asset_duration_seconds)
    )
    cover_timestamp = 0.0 if cover_timestamp_seconds is None else float(cover_timestamp_seconds)

    scenes = _copy_timing_rows(canonical_timeline.get("scenes"))
    overlays = _copy_timing_rows(canonical_timeline.get("overlays"))
    audio_tracks = _copy_timing_rows(canonical_timeline.get("audio_tracks"))
    checks = validate_media_timeline(
        creative_duration_seconds=creative_duration,
        source_asset_duration_seconds=source_duration,
        final_video_duration_seconds=final_duration,
        editing_duration_seconds=editing_duration,
        final_video_has_video_stream=final_video_has_video_stream,
        final_video_has_audio_stream=final_video_has_audio_stream,
        final_audio_duration_seconds=audio_duration,
        scenes=scenes,
        overlays=overlays,
        cover_timestamp_seconds=cover_timestamp,
        source_padded=source_padded,
        source_looped=source_looped,
    )

    fade_in, fade_out = _master_audio_fades(audio_tracks)
    failure_codes = _failure_codes(checks)
    legacy_duration_checks = _legacy_duration_mismatch_checks(
        checks=checks,
        creative_duration_seconds=creative_duration,
        source_asset_duration_seconds=source_duration,
        final_video_duration_seconds=final_duration,
        editing_duration_seconds=editing_duration,
    )
    return {
        "schema_version": "media_timeline_v1",
        "legacy_schema_version": "timeline_render_trace.v1",
        "timeline_id": canonical_timeline.get("timeline_id"),
        "creative": {"duration_seconds": creative_duration},
        "source_video": {
            "duration_seconds": source_duration,
            "path_or_uri": source_path_or_uri,
            "padded": source_padded,
            "looped": source_looped,
            "trimmed": source_trimmed,
        },
        "final_video": {
            "duration_seconds": final_duration,
            "width": final_video_width,
            "height": final_video_height,
            "fps": final_video_fps,
            "path_or_uri": final_video_path_or_uri,
            "has_video_stream": final_video_has_video_stream,
            "has_audio_stream": final_video_has_audio_stream,
            "video_codec": final_video_codec,
            "audio_codec": final_audio_codec,
        },
        "audio": {
            "present": final_video_has_audio_stream,
            "duration_seconds": audio_duration,
            "padded": audio_padded,
            "trimmed": audio_trimmed,
            "fade_in_seconds": fade_in,
            "fade_out_seconds": fade_out,
        },
        "scenes": scenes,
        "overlays": overlays,
        "cover": {"timestamp_seconds": cover_timestamp},
        "trim_pad_behavior": {
            "audio_padded": audio_padded,
            "audio_trimmed": audio_trimmed,
            "source_padded": source_padded,
            "source_looped": source_looped,
            "source_trimmed": source_trimmed,
        },
        "checks": checks,
        "passed": not failure_codes,
        "failure_codes": failure_codes,
        # Compatibility keys consumed by existing QA and package tests.
        "scene_timings": scenes,
        "overlay_timings": overlays,
        "audio_timings": audio_tracks,
        "fade_durations": [
            {
                "track_id": track.get("track_id"),
                "fade_in_seconds": track.get("fade_in_seconds"),
                "fade_out_seconds": track.get("fade_out_seconds"),
            }
            for track in audio_tracks
        ],
        "final_render_duration_seconds": final_duration,
        "source_asset_duration_seconds": source_duration,
        "duration_mismatch_checks": legacy_duration_checks,
        "cover_timestamp_seconds": cover_timestamp,
    }


def validate_media_timeline(
    *,
    creative_duration_seconds: float | None,
    source_asset_duration_seconds: float | None,
    final_video_duration_seconds: float,
    editing_duration_seconds: float | None,
    final_video_has_video_stream: bool,
    final_video_has_audio_stream: bool,
    final_audio_duration_seconds: float | None,
    scenes: Sequence[Mapping[str, Any]],
    overlays: Sequence[Mapping[str, Any]],
    cover_timestamp_seconds: float | None,
    source_padded: bool = False,
    source_looped: bool = False,
) -> dict[str, dict[str, Any]]:
    final_duration = float(final_video_duration_seconds)
    checks: dict[str, dict[str, Any]] = {}

    checks["video_stream"] = _check(
        bool(final_video_has_video_stream),
        "final_video_missing_video",
        "Final video must contain a video stream.",
    )
    checks["audio_stream"] = _check(
        bool(final_video_has_audio_stream),
        "final_video_missing_audio",
        "Final video must contain an audio stream.",
    )

    if final_audio_duration_seconds is None:
        checks["audio_video_sync"] = _check(
            False,
            "audio_video_duration_mismatch",
            "Final video audio duration is unavailable.",
        )
    else:
        audio_delta = abs(float(final_audio_duration_seconds) - final_duration)
        checks["audio_video_sync"] = _check(
            audio_delta <= AUDIO_VIDEO_SYNC_TOLERANCE_SECONDS,
            "audio_video_duration_mismatch",
            "Audio duration must match final video duration.",
            delta_seconds=audio_delta,
            tolerance_seconds=AUDIO_VIDEO_SYNC_TOLERANCE_SECONDS,
        )

    if editing_duration_seconds is not None:
        editing_delta = abs(float(editing_duration_seconds) - final_duration)
        checks["duration_alignment"] = _check(
            editing_delta <= EDITING_DURATION_TOLERANCE_SECONDS,
            "editing_duration_mismatch",
            "Editing duration must match ffprobe final duration.",
            delta_seconds=editing_delta,
            tolerance_seconds=EDITING_DURATION_TOLERANCE_SECONDS,
        )
    else:
        checks["duration_alignment"] = _check(
            False,
            "editing_duration_mismatch",
            "Editing duration is missing.",
        )

    if creative_duration_seconds is not None:
        creative_delta = abs(float(creative_duration_seconds) - final_duration)
        checks["creative_duration"] = _check(
            creative_delta <= CREATIVE_DURATION_TOLERANCE_SECONDS,
            "creative_duration_mismatch",
            "Creative timeline duration must match final video duration.",
            delta_seconds=creative_delta,
            tolerance_seconds=CREATIVE_DURATION_TOLERANCE_SECONDS,
        )
    else:
        checks["creative_duration"] = _check(
            False,
            "creative_duration_mismatch",
            "Creative timeline duration is missing.",
        )

    checks["scene_bounds"] = _validate_timed_rows(
        rows=scenes,
        final_duration_seconds=final_duration,
        failure_code="scene_exceeds_video_duration",
        label="Scene",
    )
    checks["overlay_bounds"] = _validate_timed_rows(
        rows=overlays,
        final_duration_seconds=final_duration,
        failure_code="overlay_exceeds_video_duration",
        label="Overlay",
    )

    cover_ok = (
        cover_timestamp_seconds is not None
        and 0.0 <= float(cover_timestamp_seconds) <= final_duration
    )
    checks["cover_timestamp"] = _check(
        cover_ok,
        "cover_timestamp_out_of_bounds",
        "Cover timestamp must be within final video duration.",
        timestamp_seconds=cover_timestamp_seconds,
        final_duration_seconds=final_duration,
    )

    source_ok = True
    if source_asset_duration_seconds is not None:
        source_ok = (
            (
                float(source_asset_duration_seconds) + SOURCE_DURATION_TOLERANCE_SECONDS
                >= final_duration
            )
            or source_padded
            or source_looped
        )
    checks["source_asset_duration"] = _check(
        source_ok,
        "source_asset_too_short",
        "Source asset is shorter than final video without logged padding or looping.",
        source_asset_duration_seconds=source_asset_duration_seconds,
        final_duration_seconds=final_duration,
        tolerance_seconds=SOURCE_DURATION_TOLERANCE_SECONDS,
        source_padded=source_padded,
        source_looped=source_looped,
    )
    return checks


def _validate_timed_rows(
    *,
    rows: Sequence[Mapping[str, Any]],
    final_duration_seconds: float,
    failure_code: str,
    label: str,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        start = _as_float(row.get("start_seconds"))
        end = _as_float(row.get("end_seconds"))
        if start is None or end is None or start < 0.0 or end <= start:
            failures.append(
                {
                    "index": index,
                    "start_seconds": start,
                    "end_seconds": end,
                    "reason": "invalid_span",
                }
            )
            continue
        if end > final_duration_seconds + TIMING_BOUNDS_TOLERANCE_SECONDS:
            failures.append(
                {
                    "index": index,
                    "start_seconds": start,
                    "end_seconds": end,
                    "final_duration_seconds": final_duration_seconds,
                    "reason": "exceeds_final_duration",
                }
            )
    return _check(
        not failures,
        failure_code,
        f"{label} timings must stay within final video duration.",
        failures=failures,
        tolerance_seconds=TIMING_BOUNDS_TOLERANCE_SECONDS,
    )


def _check(passed: bool, code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "code": code,
        "message": message,
        **details,
    }


def _failure_codes(checks: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return [
        str(check.get("code"))
        for check in checks.values()
        if check.get("passed") is False and check.get("code")
    ]


def _copy_timing_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            rows.append({str(key): item[key] for key in item})
    return rows


def _master_audio_fades(
    audio_tracks: Sequence[Mapping[str, Any]],
) -> tuple[float | None, float | None]:
    if not audio_tracks:
        return (None, None)
    master = next(
        (track for track in audio_tracks if str(track.get("role", "")).lower() == "master"),
        audio_tracks[0],
    )
    return (_as_float(master.get("fade_in_seconds")), _as_float(master.get("fade_out_seconds")))


def _legacy_duration_mismatch_checks(
    *,
    checks: Mapping[str, Mapping[str, Any]],
    creative_duration_seconds: float | None,
    source_asset_duration_seconds: float | None,
    final_video_duration_seconds: float,
    editing_duration_seconds: float | None,
) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    for key in ("duration_alignment", "creative_duration", "source_asset_duration"):
        check = checks.get(key)
        if check is not None and check.get("passed") is False:
            mismatches.append(
                {
                    "code": check.get("code"),
                    "delta_seconds": check.get("delta_seconds"),
                    "tolerance_seconds": check.get("tolerance_seconds"),
                }
            )
    return {
        "status": "pass" if not mismatches else "fail",
        "requested_provider_duration_seconds": creative_duration_seconds,
        "source_clip_duration_seconds": source_asset_duration_seconds,
        "scene_plan_duration_seconds": creative_duration_seconds,
        "final_rendered_duration_seconds": final_video_duration_seconds,
        "editing_duration_seconds": editing_duration_seconds,
        "mismatches": mismatches,
    }


def _as_float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "AUDIO_VIDEO_SYNC_TOLERANCE_SECONDS",
    "CREATIVE_DURATION_TOLERANCE_SECONDS",
    "EDITING_DURATION_TOLERANCE_SECONDS",
    "SOURCE_DURATION_TOLERANCE_SECONDS",
    "TIMING_BOUNDS_TOLERANCE_SECONDS",
    "build_timeline_render_trace",
    "validate_media_timeline",
]
