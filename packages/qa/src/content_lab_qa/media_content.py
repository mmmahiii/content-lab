"""QA gates that look at the decoded media, not just container metadata.

``format.py`` only checks that streams exist with the right shape, so a reel that is silent,
black, or frozen for long stretches used to pass. These gates decode the final MP4 once with
FFmpeg (``blackdetect``, ``freezedetect``, ``volumedetect``, ``silencedetect``) and check the
rendered overlay manifest for stretches with no on-screen text.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult

MEDIA_CONTENT_GATE_NAME = "media_content"
AUDIO_CONTENT_GATE_NAME = "audio_content"
OVERLAY_COVERAGE_GATE_NAME = "overlay_coverage"

# Final MP4 format tag the editor writes when the voiceover came from the mock TTS provider.
MOCK_VOICEOVER_TAG_KEY = "comment"
MOCK_VOICEOVER_TAG_VALUE = "content_lab_voiceover=mock"

DEFAULT_TIMEOUT_SECONDS = 180.0
SILENCE_FLOOR_DB = -120.0
_ANALYSIS_WIDTH = 270  # detection on a downscaled copy is ~16x cheaper and just as reliable


class MediaContentConstraints(BaseModel):
    """Thresholds for decoded-media QA."""

    model_config = ConfigDict(extra="forbid")

    max_blank_segment_seconds: float = Field(default=1.0, gt=0.0, le=30.0)
    max_static_segment_seconds: float = Field(default=1.0, gt=0.0, le=30.0)
    # blackdetect: a pixel is "black" below this luma ratio; a frame is black when this share
    # of its pixels is black. 0.98 lets small captions on a black card still count as blank.
    black_pixel_threshold: float = Field(default=0.10, ge=0.0, le=1.0)
    black_picture_ratio: float = Field(default=0.98, ge=0.0, le=1.0)
    # freezedetect noise tolerance (dB); -60 dB is FFmpeg's default.
    freeze_noise_db: float = Field(default=-60.0, le=0.0)
    silence_threshold_db: float = Field(default=-60.0, le=0.0)
    min_mean_volume_db: float = Field(default=-60.0, le=0.0)
    max_silent_segment_seconds: float = Field(default=2.0, gt=0.0, le=60.0)
    max_overlay_gap_seconds: float = Field(default=0.5, ge=0.0, le=30.0)


@dataclass(frozen=True, slots=True)
class MediaInterval:
    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        return max(self.end_seconds - self.start_seconds, 0.0)

    def as_dict(self) -> dict[str, float]:
        return {
            "start_seconds": round(self.start_seconds, 3),
            "end_seconds": round(self.end_seconds, 3),
            "duration_seconds": round(self.duration_seconds, 3),
        }


@dataclass(frozen=True, slots=True)
class MediaContentAnalysis:
    """What FFmpeg saw when decoding the final video."""

    duration_seconds: float
    has_audio: bool
    black_segments: tuple[MediaInterval, ...] = ()
    frozen_segments: tuple[MediaInterval, ...] = ()
    silent_segments: tuple[MediaInterval, ...] = ()
    mean_volume_db: float | None = None
    max_volume_db: float | None = None
    format_tags: Mapping[str, str] = field(default_factory=dict)

    @property
    def is_mock_voiceover(self) -> bool:
        return (
            self.format_tags.get(MOCK_VOICEOVER_TAG_KEY, "").strip().lower()
            == MOCK_VOICEOVER_TAG_VALUE
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "duration_seconds": round(self.duration_seconds, 3),
            "has_audio": self.has_audio,
            "black_segments": [item.as_dict() for item in self.black_segments],
            "frozen_segments": [item.as_dict() for item in self.frozen_segments],
            "silent_segments": [item.as_dict() for item in self.silent_segments],
            "mean_volume_db": self.mean_volume_db,
            "max_volume_db": self.max_volume_db,
            "mock_voiceover": self.is_mock_voiceover,
        }


def analyze_media_content(
    video_path: str | Path,
    *,
    constraints: MediaContentConstraints | None = None,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> MediaContentAnalysis:
    """Decode ``video_path`` once and collect black, frozen and silent intervals."""

    effective = constraints or MediaContentConstraints()
    path = Path(video_path)
    probe = _probe(path, ffprobe_bin=ffprobe_bin, timeout_seconds=timeout_seconds)
    duration = probe["duration_seconds"]
    has_audio = probe["has_audio"]
    # Detect anything at least half the allowed length so short-but-adjacent runs still show.
    min_visual = min(effective.max_blank_segment_seconds, effective.max_static_segment_seconds)
    video_filter = (
        f"scale={_ANALYSIS_WIDTH}:-2,"
        f"blackdetect=d={min_visual / 2:.3f}:pix_th={effective.black_pixel_threshold:.3f}"
        f":pic_th={effective.black_picture_ratio:.3f},"
        f"freezedetect=n={effective.freeze_noise_db:.1f}dB:d={min_visual / 2:.3f}"
    )
    command = [ffmpeg_bin, "-hide_banner", "-nostats", "-i", str(path), "-map", "0:v:0"]
    command += ["-vf", video_filter]
    if has_audio:
        command += [
            "-map",
            "0:a:0",
            "-af",
            f"volumedetect,silencedetect=n={effective.silence_threshold_db:.1f}dB:d=0.5",
        ]
    command += ["-f", "null", "-"]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"ffmpeg media analysis failed for {path}: {completed.stderr.strip()[-2000:]}"
        )
    log = completed.stderr
    return MediaContentAnalysis(
        duration_seconds=duration,
        has_audio=has_audio,
        black_segments=_parse_black_segments(log, duration_seconds=duration),
        frozen_segments=_parse_marker_segments(
            log,
            start_pattern=r"lavfi\.freezedetect\.freeze_start:\s*([0-9.]+)",
            end_pattern=r"lavfi\.freezedetect\.freeze_end:\s*([0-9.]+)",
            duration_seconds=duration,
        ),
        silent_segments=_parse_marker_segments(
            log,
            start_pattern=r"silence_start:\s*(-?[0-9.]+)",
            end_pattern=r"silence_end:\s*([0-9.]+)",
            duration_seconds=duration,
        ),
        mean_volume_db=_parse_volume(log, "mean_volume"),
        max_volume_db=_parse_volume(log, "max_volume"),
        format_tags=probe["tags"],
    )


def evaluate_media_content_qa(
    *,
    analysis: MediaContentAnalysis,
    constraints: MediaContentConstraints | None = None,
) -> QAResult:
    """Fail when any visual stretch longer than the limit is black or frozen."""

    effective = constraints or MediaContentConstraints()
    findings: list[dict[str, Any]] = []
    for segment in analysis.black_segments:
        if segment.duration_seconds > effective.max_blank_segment_seconds:
            findings.append(
                {
                    "code": "video_blank_segment",
                    "severity": "fail",
                    "message": (
                        f"Video is black for {segment.duration_seconds:.2f}s "
                        f"({segment.start_seconds:.2f}-{segment.end_seconds:.2f}s)."
                    ),
                    "details": segment.as_dict(),
                }
            )
    for segment in analysis.frozen_segments:
        if segment.duration_seconds > effective.max_static_segment_seconds:
            findings.append(
                {
                    "code": "video_static_segment",
                    "severity": "fail",
                    "message": (
                        f"Video is frozen for {segment.duration_seconds:.2f}s "
                        f"({segment.start_seconds:.2f}-{segment.end_seconds:.2f}s)."
                    ),
                    "details": segment.as_dict(),
                }
            )
    verdict = QAVerdict.FAIL if findings else QAVerdict.PASS
    message = (
        f"Video has {len(findings)} blank or static segment(s) longer than "
        f"{effective.max_blank_segment_seconds:.1f}s."
        if findings
        else "Video has no blank or static segments."
    )
    return QAResult(
        gate_name=MEDIA_CONTENT_GATE_NAME,
        verdict=verdict,
        message=message,
        details={"findings": findings, "analysis": analysis.as_dict()},
    )


def evaluate_audio_content_qa(
    *,
    analysis: MediaContentAnalysis,
    voiceover: Mapping[str, Any] | None = None,
    expect_voiceover: bool = False,
    constraints: MediaContentConstraints | None = None,
) -> QAResult:
    """Fail silent reels; flag mock voiceovers so they are never mistaken for real voice."""

    effective = constraints or MediaContentConstraints()
    findings: list[dict[str, Any]] = []
    if not analysis.has_audio:
        findings.append(
            {
                "code": "audio_missing",
                "severity": "fail",
                "message": "Final video has no audio stream.",
                "details": {},
            }
        )
    else:
        mean = analysis.mean_volume_db
        if mean is None or mean < effective.min_mean_volume_db:
            findings.append(
                {
                    "code": "audio_silent",
                    "severity": "fail",
                    "message": (
                        f"Audio is silent (mean volume {mean if mean is not None else 'n/a'} dB, "
                        f"minimum {effective.min_mean_volume_db:.0f} dB)."
                    ),
                    "details": {
                        "mean_volume_db": mean,
                        "max_volume_db": analysis.max_volume_db,
                    },
                }
            )
        else:
            for segment in analysis.silent_segments:
                if segment.duration_seconds > effective.max_silent_segment_seconds:
                    findings.append(
                        {
                            # Dead air between narration lines is a pacing issue, not a
                            # silent reel: advisory, so it shows up without blocking.
                            "code": "audio_silent_segment",
                            "severity": "warn",
                            "message": (
                                f"Audio is silent for {segment.duration_seconds:.2f}s "
                                f"({segment.start_seconds:.2f}-{segment.end_seconds:.2f}s)."
                            ),
                            "details": segment.as_dict(),
                        }
                    )
    voiceover_provider = str((voiceover or {}).get("provider") or "").strip().lower() or None
    if expect_voiceover and voiceover_provider is None:
        findings.append(
            {
                "code": "voiceover_missing",
                "severity": "fail",
                "message": "The script has narration but no voiceover was rendered.",
                "details": {},
            }
        )
    mock = analysis.is_mock_voiceover or voiceover_provider == "mock"
    if mock:
        findings.append(
            {
                "code": "mock_voiceover",
                "severity": "warn",
                "message": "Voiceover is the deterministic mock (tone), not real speech.",
                "details": {"provider": voiceover_provider or "mock"},
            }
        )

    if any(item["severity"] == "fail" for item in findings):
        verdict = QAVerdict.FAIL
        message = "; ".join(item["message"] for item in findings if item["severity"] == "fail")
    elif findings:
        verdict = QAVerdict.WARN
        message = "; ".join(item["message"] for item in findings)
    else:
        verdict = QAVerdict.PASS
        message = "Audio present and not silent."
    return QAResult(
        gate_name=AUDIO_CONTENT_GATE_NAME,
        verdict=verdict,
        message=message,
        details={
            "findings": findings,
            "mean_volume_db": analysis.mean_volume_db,
            "max_volume_db": analysis.max_volume_db,
            "silent_segments": [item.as_dict() for item in analysis.silent_segments],
            "mock_voiceover": mock,
            "voiceover_provider": voiceover_provider,
        },
    )


def evaluate_overlay_coverage_qa(
    *,
    rendered_overlay_manifest: Mapping[str, Any] | None,
    final_duration_seconds: float,
    constraints: MediaContentConstraints | None = None,
) -> QAResult:
    """Fail when on-screen text leaves a stretch of the reel uncovered (e.g. a blank tail)."""

    effective = constraints or MediaContentConstraints()
    duration = max(float(final_duration_seconds), 0.0)
    if not rendered_overlay_manifest or "overlays" not in rendered_overlay_manifest:
        # No manifest to judge (fixtures, legacy outputs); overlay_text_fidelity reports it.
        return QAResult(
            gate_name=OVERLAY_COVERAGE_GATE_NAME,
            verdict=QAVerdict.SKIP,
            message="No rendered overlay manifest; overlay coverage not evaluated.",
            details={"findings": []},
        )
    overlays = rendered_overlay_manifest.get("overlays")
    intervals: list[MediaInterval] = []
    if isinstance(overlays, Sequence):
        for item in overlays:
            if not isinstance(item, Mapping):
                continue
            start = _as_float(item.get("visible_start_seconds", item.get("start_seconds")))
            end = _as_float(item.get("visible_end_seconds", item.get("end_seconds")))
            if start is None or end is None or end <= start:
                continue
            intervals.append(MediaInterval(max(start, 0.0), min(end, duration)))
    gaps = uncovered_intervals(intervals, duration_seconds=duration)
    long_gaps = [gap for gap in gaps if gap.duration_seconds > effective.max_overlay_gap_seconds]
    findings = [
        {
            "code": "overlay_coverage_gap",
            "severity": "fail",
            "message": (
                f"No on-screen text for {gap.duration_seconds:.2f}s "
                f"({gap.start_seconds:.2f}-{gap.end_seconds:.2f}s)."
            ),
            "details": gap.as_dict(),
        }
        for gap in long_gaps
    ]
    covered = duration - sum(gap.duration_seconds for gap in gaps)
    return QAResult(
        gate_name=OVERLAY_COVERAGE_GATE_NAME,
        verdict=QAVerdict.FAIL if findings else QAVerdict.PASS,
        message=(
            f"Overlays leave {len(findings)} uncovered stretch(es) of the reel."
            if findings
            else "Overlays cover the full reel."
        ),
        details={
            "findings": findings,
            "duration_seconds": round(duration, 3),
            "covered_seconds": round(covered, 3),
            "gaps": [gap.as_dict() for gap in gaps],
        },
    )


def uncovered_intervals(
    intervals: Sequence[MediaInterval],
    *,
    duration_seconds: float,
) -> list[MediaInterval]:
    """Return the parts of ``[0, duration]`` not covered by ``intervals``."""

    gaps: list[MediaInterval] = []
    cursor = 0.0
    for item in sorted(intervals, key=lambda it: (it.start_seconds, it.end_seconds)):
        if item.start_seconds > cursor + 1e-3:
            gaps.append(MediaInterval(cursor, min(item.start_seconds, duration_seconds)))
        cursor = max(cursor, item.end_seconds)
    if cursor < duration_seconds - 1e-3:
        gaps.append(MediaInterval(cursor, duration_seconds))
    return [gap for gap in gaps if gap.duration_seconds > 0]


def _probe(path: Path, *, ffprobe_bin: str, timeout_seconds: float) -> dict[str, Any]:
    completed = subprocess.run(
        [ffprobe_bin, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {completed.stderr.strip()}")
    payload = json.loads(completed.stdout or "{}")
    streams = payload.get("streams") or []
    fmt = payload.get("format") or {}
    raw_tags = fmt.get("tags") or {}
    return {
        "duration_seconds": float(fmt.get("duration") or 0.0),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams if isinstance(s, dict)),
        "tags": {str(k).lower(): str(v) for k, v in raw_tags.items()},
    }


def _parse_black_segments(log: str, *, duration_seconds: float) -> tuple[MediaInterval, ...]:
    segments = [
        MediaInterval(float(start), min(float(end), duration_seconds))
        for start, end in re.findall(r"black_start:\s*([0-9.]+)\s+black_end:\s*([0-9.]+)", log)
    ]
    return tuple(segments)


def _parse_marker_segments(
    log: str,
    *,
    start_pattern: str,
    end_pattern: str,
    duration_seconds: float,
) -> tuple[MediaInterval, ...]:
    """Pair start/end markers in log order; an unterminated run ends at the media end."""

    events: list[tuple[int, str, float]] = []
    for match in re.finditer(start_pattern, log):
        events.append((match.start(), "start", max(float(match.group(1)), 0.0)))
    for match in re.finditer(end_pattern, log):
        events.append((match.start(), "end", float(match.group(1))))
    events.sort()
    segments: list[MediaInterval] = []
    open_start: float | None = None
    for _, kind, value in events:
        if kind == "start":
            if open_start is None:
                open_start = value
        elif open_start is not None:
            segments.append(MediaInterval(open_start, min(value, duration_seconds)))
            open_start = None
    if open_start is not None and duration_seconds > open_start:
        segments.append(MediaInterval(open_start, duration_seconds))
    return tuple(segments)


def _parse_volume(log: str, key: str) -> float | None:
    match = re.search(rf"{key}:\s*(-?(?:[0-9.]+|inf))\s*dB", log)
    if match is None:
        return None
    raw = match.group(1)
    if raw == "-inf":
        # Digital silence. Keep the value finite so QA details stay valid JSON (JSONB).
        return SILENCE_FLOOR_DB
    return max(float(raw), SILENCE_FLOOR_DB)


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


__all__ = [
    "AUDIO_CONTENT_GATE_NAME",
    "MEDIA_CONTENT_GATE_NAME",
    "MOCK_VOICEOVER_TAG_KEY",
    "MOCK_VOICEOVER_TAG_VALUE",
    "OVERLAY_COVERAGE_GATE_NAME",
    "SILENCE_FLOOR_DB",
    "MediaContentAnalysis",
    "MediaContentConstraints",
    "MediaInterval",
    "analyze_media_content",
    "evaluate_audio_content_qa",
    "evaluate_media_content_qa",
    "evaluate_overlay_coverage_qa",
    "uncovered_intervals",
]
