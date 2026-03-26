"""Format QA checks for canonical final videos and cover images."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult

DEFAULT_FINAL_VIDEO_FILENAME = "final_video.mp4"
DEFAULT_COVER_FILENAME = "cover.png"
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_MIN_DURATION_SECONDS = 0.1
DEFAULT_MAX_DURATION_SECONDS = 60.0
DEFAULT_TIMEOUT_SECONDS = 30.0


class FormatQAConstraints(BaseModel):
    """Expected media properties for ready-to-post outputs."""

    final_video_width: int = DEFAULT_WIDTH
    final_video_height: int = DEFAULT_HEIGHT
    cover_width: int = DEFAULT_WIDTH
    cover_height: int = DEFAULT_HEIGHT
    min_duration_seconds: float = DEFAULT_MIN_DURATION_SECONDS
    max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS
    require_audio: bool = True


class ProbedMedia(BaseModel):
    """Normalized subset of media metadata needed by format QA."""

    path: str
    exists: bool
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    has_audio: bool | None = None
    error: str = ""

    @property
    def can_validate(self) -> bool:
        return self.exists and not self.error


class FormatQAReport(BaseModel):
    """Structured format QA output for flows and web views."""

    gate_name: str = "format"
    verdict: QAVerdict
    message: str = ""
    checks: tuple[QAResult, ...] = Field(default_factory=tuple)
    failure_reasons: tuple[str, ...] = Field(default_factory=tuple)
    constraints: FormatQAConstraints = Field(default_factory=FormatQAConstraints)
    final_video: ProbedMedia
    cover: ProbedMedia

    @property
    def passed(self) -> bool:
        return self.verdict in (QAVerdict.PASS, QAVerdict.SKIP)


def evaluate_reel_package_format(
    package_directory: str | Path,
    *,
    constraints: FormatQAConstraints | None = None,
    final_video_filename: str = DEFAULT_FINAL_VIDEO_FILENAME,
    cover_filename: str = DEFAULT_COVER_FILENAME,
    ffprobe_bin: str = "ffprobe",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> FormatQAReport:
    """Evaluate format QA for a canonical local reel-package directory."""

    resolved_directory = Path(package_directory)
    return evaluate_format_qa(
        final_video_path=resolved_directory / final_video_filename,
        cover_path=resolved_directory / cover_filename,
        constraints=constraints,
        ffprobe_bin=ffprobe_bin,
        timeout_seconds=timeout_seconds,
    )


def evaluate_format_qa(
    *,
    final_video_path: str | Path,
    cover_path: str | Path,
    constraints: FormatQAConstraints | None = None,
    ffprobe_bin: str = "ffprobe",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> FormatQAReport:
    """Evaluate final-video and cover media against format requirements."""

    effective_constraints = constraints or FormatQAConstraints()
    final_video = _probe_media(
        final_video_path,
        ffprobe_bin=ffprobe_bin,
        timeout_seconds=timeout_seconds,
    )
    cover = _probe_media(
        cover_path,
        ffprobe_bin=ffprobe_bin,
        timeout_seconds=timeout_seconds,
    )

    checks = (
        _resolution_check(
            gate_name="final_video_dimensions",
            label="Final video",
            media=final_video,
            expected_width=effective_constraints.final_video_width,
            expected_height=effective_constraints.final_video_height,
        ),
        _duration_check(
            media=final_video,
            min_duration_seconds=effective_constraints.min_duration_seconds,
            max_duration_seconds=effective_constraints.max_duration_seconds,
        ),
        _audio_check(
            media=final_video,
            require_audio=effective_constraints.require_audio,
        ),
        _cover_exists_check(cover),
        _resolution_check(
            gate_name="cover_dimensions",
            label="Cover image",
            media=cover,
            expected_width=effective_constraints.cover_width,
            expected_height=effective_constraints.cover_height,
            skip_if_missing=True,
        ),
    )
    return _build_report(
        checks=checks,
        constraints=effective_constraints,
        final_video=final_video,
        cover=cover,
    )


def _build_report(
    *,
    checks: tuple[QAResult, ...],
    constraints: FormatQAConstraints,
    final_video: ProbedMedia,
    cover: ProbedMedia,
) -> FormatQAReport:
    failed_checks = tuple(check for check in checks if check.verdict == QAVerdict.FAIL)
    failure_reasons = tuple(check.message for check in failed_checks if check.message)

    if failure_reasons:
        message = "; ".join(failure_reasons)
        verdict = QAVerdict.FAIL
    else:
        message = "Final video and cover satisfy the format QA constraints."
        verdict = QAVerdict.PASS

    return FormatQAReport(
        verdict=verdict,
        message=message,
        checks=checks,
        failure_reasons=failure_reasons,
        constraints=constraints,
        final_video=final_video,
        cover=cover,
    )


def _cover_exists_check(media: ProbedMedia) -> QAResult:
    if media.exists:
        return QAResult(
            gate_name="cover_exists",
            verdict=QAVerdict.PASS,
            message="Cover image exists.",
            details={"path": media.path},
        )

    return QAResult(
        gate_name="cover_exists",
        verdict=QAVerdict.FAIL,
        message=f"Cover image is missing at {media.path}.",
        details={"path": media.path},
    )


def _resolution_check(
    *,
    gate_name: str,
    label: str,
    media: ProbedMedia,
    expected_width: int,
    expected_height: int,
    skip_if_missing: bool = False,
) -> QAResult:
    if not media.exists:
        verdict = QAVerdict.SKIP if skip_if_missing else QAVerdict.FAIL
        return QAResult(
            gate_name=gate_name,
            verdict=verdict,
            message=f"{label} is missing at {media.path}.",
            details={
                "path": media.path,
                "expected_width": expected_width,
                "expected_height": expected_height,
            },
        )

    if media.error:
        return QAResult(
            gate_name=gate_name,
            verdict=QAVerdict.FAIL,
            message=f"Unable to inspect {label.lower()}: {media.error}",
            details={
                "path": media.path,
                "expected_width": expected_width,
                "expected_height": expected_height,
            },
        )

    if media.width is None or media.height is None:
        return QAResult(
            gate_name=gate_name,
            verdict=QAVerdict.FAIL,
            message=f"{label} dimensions are unavailable for {media.path}.",
            details={
                "path": media.path,
                "expected_width": expected_width,
                "expected_height": expected_height,
            },
        )

    if media.width != expected_width or media.height != expected_height:
        return QAResult(
            gate_name=gate_name,
            verdict=QAVerdict.FAIL,
            message=(
                f"{label} dimensions must be {expected_width}x{expected_height}; "
                f"got {media.width}x{media.height}."
            ),
            details={
                "path": media.path,
                "actual_width": media.width,
                "actual_height": media.height,
                "expected_width": expected_width,
                "expected_height": expected_height,
            },
        )

    return QAResult(
        gate_name=gate_name,
        verdict=QAVerdict.PASS,
        message=f"{label} dimensions are valid.",
        details={
            "path": media.path,
            "actual_width": media.width,
            "actual_height": media.height,
            "expected_width": expected_width,
            "expected_height": expected_height,
        },
    )


def _duration_check(
    *,
    media: ProbedMedia,
    min_duration_seconds: float,
    max_duration_seconds: float,
) -> QAResult:
    if not media.exists:
        return QAResult(
            gate_name="final_video_duration",
            verdict=QAVerdict.FAIL,
            message=f"Final video is missing at {media.path}.",
            details={
                "path": media.path,
                "min_duration_seconds": min_duration_seconds,
                "max_duration_seconds": max_duration_seconds,
            },
        )

    if media.error:
        return QAResult(
            gate_name="final_video_duration",
            verdict=QAVerdict.FAIL,
            message=f"Unable to inspect final video duration: {media.error}",
            details={
                "path": media.path,
                "min_duration_seconds": min_duration_seconds,
                "max_duration_seconds": max_duration_seconds,
            },
        )

    if media.duration_seconds is None:
        return QAResult(
            gate_name="final_video_duration",
            verdict=QAVerdict.FAIL,
            message=f"Final video duration is unavailable for {media.path}.",
            details={
                "path": media.path,
                "min_duration_seconds": min_duration_seconds,
                "max_duration_seconds": max_duration_seconds,
            },
        )

    if not min_duration_seconds <= media.duration_seconds <= max_duration_seconds:
        return QAResult(
            gate_name="final_video_duration",
            verdict=QAVerdict.FAIL,
            message=(
                "Final video duration must be between "
                f"{_format_seconds(min_duration_seconds)} and "
                f"{_format_seconds(max_duration_seconds)}; "
                f"got {_format_seconds(media.duration_seconds)}."
            ),
            details={
                "path": media.path,
                "actual_duration_seconds": media.duration_seconds,
                "min_duration_seconds": min_duration_seconds,
                "max_duration_seconds": max_duration_seconds,
            },
        )

    return QAResult(
        gate_name="final_video_duration",
        verdict=QAVerdict.PASS,
        message="Final video duration is valid.",
        details={
            "path": media.path,
            "actual_duration_seconds": media.duration_seconds,
            "min_duration_seconds": min_duration_seconds,
            "max_duration_seconds": max_duration_seconds,
        },
    )


def _audio_check(*, media: ProbedMedia, require_audio: bool) -> QAResult:
    if not require_audio:
        return QAResult(
            gate_name="final_video_audio",
            verdict=QAVerdict.SKIP,
            message="Final video audio presence is not required.",
            details={"path": media.path},
        )

    if not media.exists:
        return QAResult(
            gate_name="final_video_audio",
            verdict=QAVerdict.FAIL,
            message=f"Final video is missing at {media.path}.",
            details={"path": media.path, "require_audio": require_audio},
        )

    if media.error:
        return QAResult(
            gate_name="final_video_audio",
            verdict=QAVerdict.FAIL,
            message=f"Unable to inspect final video audio presence: {media.error}",
            details={"path": media.path, "require_audio": require_audio},
        )

    if media.has_audio is not True:
        return QAResult(
            gate_name="final_video_audio",
            verdict=QAVerdict.FAIL,
            message=f"Final video must include an audio track: {media.path}.",
            details={"path": media.path, "require_audio": require_audio},
        )

    return QAResult(
        gate_name="final_video_audio",
        verdict=QAVerdict.PASS,
        message="Final video includes an audio track.",
        details={"path": media.path, "require_audio": require_audio},
    )


def _probe_media(
    path: str | Path,
    *,
    ffprobe_bin: str,
    timeout_seconds: float,
) -> ProbedMedia:
    resolved_path = Path(path).expanduser().resolve(strict=False)
    if not resolved_path.exists() or not resolved_path.is_file():
        return ProbedMedia(path=str(resolved_path), exists=False)

    command = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(resolved_path),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return ProbedMedia(
            path=str(resolved_path),
            exists=True,
            error=f"Unable to find executable '{ffprobe_bin}'.",
        )
    except subprocess.TimeoutExpired:
        return ProbedMedia(
            path=str(resolved_path),
            exists=True,
            error=f"ffprobe timed out after {_format_seconds(timeout_seconds)}.",
        )

    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "no output captured"
        return ProbedMedia(
            path=str(resolved_path),
            exists=True,
            error=details,
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return ProbedMedia(
            path=str(resolved_path),
            exists=True,
            error=f"ffprobe returned invalid JSON: {exc.msg}",
        )

    if not isinstance(payload, dict):
        return ProbedMedia(
            path=str(resolved_path),
            exists=True,
            error="ffprobe returned a non-object payload.",
        )

    streams = payload.get("streams")
    if not isinstance(streams, list):
        return ProbedMedia(
            path=str(resolved_path),
            exists=True,
            error="ffprobe returned invalid stream metadata.",
        )

    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if video_stream is None:
        return ProbedMedia(
            path=str(resolved_path),
            exists=True,
            error="Media file does not contain a video stream.",
        )

    width = _coerce_int(video_stream.get("width"))
    height = _coerce_int(video_stream.get("height"))
    duration_seconds = _duration_seconds(payload=payload, video_stream=video_stream)
    has_audio = any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams
    )

    return ProbedMedia(
        path=str(resolved_path),
        exists=True,
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        has_audio=has_audio,
    )


def _duration_seconds(
    *, payload: dict[str, object], video_stream: dict[str, object]
) -> float | None:
    duration_raw = video_stream.get("duration")
    if duration_raw in (None, "", "N/A"):
        format_payload = payload.get("format")
        if isinstance(format_payload, dict):
            duration_raw = format_payload.get("duration")
    return _coerce_float(duration_raw)


def _coerce_int(value: object) -> int | None:
    if value in (None, "", "N/A"):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return int(float(value))
            except ValueError:
                return None
    return None


def _coerce_float(value: object) -> float | None:
    if value in (None, "", "N/A"):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _format_seconds(value: float) -> str:
    return f"{value:.3f}s"


__all__ = [
    "DEFAULT_COVER_FILENAME",
    "DEFAULT_FINAL_VIDEO_FILENAME",
    "FormatQAConstraints",
    "FormatQAReport",
    "ProbedMedia",
    "evaluate_format_qa",
    "evaluate_reel_package_format",
]
