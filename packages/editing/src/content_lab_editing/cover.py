"""Cover frame extraction helpers for rendered editing outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from content_lab_editing.ffmpeg import probe_media, run_ffmpeg

DEFAULT_COVER_FILENAME = "cover.png"
DEFAULT_COVER_TIMESTAMP_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class CoverFrameArtifact:
    """Metadata for a deterministic cover frame export."""

    image_path: Path
    timestamp_seconds: float


def resolve_cover_frame_timestamp(
    *,
    duration_seconds: float | None,
    default_timestamp_seconds: float = DEFAULT_COVER_TIMESTAMP_SECONDS,
) -> float:
    """Choose a stable timestamp that stays inside the available media duration."""

    safe_default = max(default_timestamp_seconds, 0.0)
    if duration_seconds is None:
        return safe_default

    bounded_duration = max(duration_seconds, 0.0)
    if bounded_duration == 0.0:
        return 0.0
    return min(safe_default, bounded_duration / 2.0)


def extract_cover_frame(
    *,
    video_path: str | Path,
    output_path: str | Path,
    timestamp_seconds: float | None = None,
    duration_seconds: float | None = None,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> CoverFrameArtifact:
    """Extract a PNG cover frame from a rendered clip."""

    resolved_video_path = Path(video_path)
    resolved_output_path = Path(output_path)
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)

    effective_duration = duration_seconds
    if effective_duration is None:
        metadata = probe_media(resolved_video_path, ffprobe_bin=ffprobe_bin)
        if metadata.format.duration_seconds is not None:
            effective_duration = metadata.format.duration_seconds
        elif metadata.video_streams:
            effective_duration = metadata.video_streams[0].duration_seconds

    resolved_timestamp = (
        resolve_cover_frame_timestamp(
            duration_seconds=effective_duration,
        )
        if timestamp_seconds is None
        else max(timestamp_seconds, 0.0)
    )

    run_ffmpeg(
        [
            "-y",
            "-ss",
            f"{resolved_timestamp:.3f}",
            "-i",
            resolved_video_path,
            "-frames:v",
            "1",
            "-an",
            "-map_metadata",
            "-1",
            str(resolved_output_path),
        ],
        ffmpeg_bin=ffmpeg_bin,
    )

    return CoverFrameArtifact(
        image_path=resolved_output_path,
        timestamp_seconds=resolved_timestamp,
    )


__all__ = [
    "CoverFrameArtifact",
    "DEFAULT_COVER_FILENAME",
    "DEFAULT_COVER_TIMESTAMP_SECONDS",
    "extract_cover_frame",
    "resolve_cover_frame_timestamp",
]
