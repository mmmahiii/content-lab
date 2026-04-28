"""Deterministic phase-1 single-clip editor backed by FFmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from content_lab_editing.cover import DEFAULT_COVER_FILENAME, extract_cover_frame
from content_lab_editing.edit_plan import SceneAwareEditPlan
from content_lab_editing.overlays import (
    OverlayTimeline,
    build_overlay_render_trace,
    build_overlay_video_filter,
)
from content_lab_editing.templates import (
    EditorialTemplate,
    apply_editorial_template,
)
from content_lab_storage.paths import OVERLAY_RENDER_TRACE_FILENAME

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
FINAL_VIDEO_FILENAME = "final_video.mp4"
FINAL_COVER_FILENAME = DEFAULT_COVER_FILENAME
PHASE1_TEMPLATE_VERSION = "basic_vertical_v1"
_AUDIO_CHANNEL_LAYOUT = "stereo"
_AUDIO_SAMPLE_RATE = 48_000
_VIDEO_FILTER = (
    f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,"
    f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
    "setsar=1"
)
_CONTENT_TYPE_EXTENSIONS = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}


class RetrievedStorageObject(Protocol):
    """Minimal object payload needed for local staging."""

    body: bytes
    content_type: str | None


class ObjectStorageClient(Protocol):
    """Storage boundary for downloading staged editing inputs."""

    def get_object(self, *, storage_uri: str) -> RetrievedStorageObject: ...


@dataclass(frozen=True, slots=True)
class MediaProbe:
    """Subset of media properties needed by the phase-1 editor."""

    width: int
    height: int
    duration_seconds: float
    has_audio_track: bool


@dataclass(frozen=True, slots=True)
class BasicEditorArtifact:
    """Local artifact produced by the narrow phase-1 editor template."""

    template_version: str
    source_uri: str
    staged_source_path: Path
    staged_segment_paths: tuple[Path, ...]
    final_video_path: Path
    cover_image_path: Path
    width: int
    height: int
    duration_seconds: float
    cover_frame_timestamp_seconds: float
    source_had_audio_track: bool
    has_audio_track: bool
    editorial_template_id: str | None = None
    editorial_template_version: str | None = None
    applied_edit_plan: SceneAwareEditPlan | None = None
    overlay_render_trace_path: Path | None = None
    overlay_render_trace: dict[str, Any] | None = None


def _persist_overlay_render_trace(
    *,
    output_dir: Path,
    base_filter: str,
    timeline: OverlayTimeline | None,
    clip_duration_seconds: float | None,
) -> tuple[Path, dict[str, Any]]:
    payload = build_overlay_render_trace(
        base_filter=base_filter,
        timeline=timeline,
        clip_duration_seconds=clip_duration_seconds,
        phase1_template_version=PHASE1_TEMPLATE_VERSION,
    )
    trace_path = output_dir / OVERLAY_RENDER_TRACE_FILENAME
    trace_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return trace_path, payload


def render_basic_vertical_edit(
    *,
    source_uri: str | Path,
    workdir: str | Path,
    storage_client: ObjectStorageClient | None = None,
    overlay_timeline: OverlayTimeline | None = None,
    edit_plan: SceneAwareEditPlan | None = None,
    editorial_template: EditorialTemplate | None = None,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> BasicEditorArtifact:
    """Stage one source clip and export a phase-1 vertical MP4 locally."""

    normalized_source_uri = _normalize_source_uri(source_uri)
    resolved_workdir = Path(workdir)
    staged_dir = resolved_workdir / "staged"
    output_dir = resolved_workdir / "output"
    staged_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if edit_plan is not None:
        applied_plan = edit_plan
        if editorial_template is not None:
            applied_plan = apply_editorial_template(
                plan=edit_plan,
                template=editorial_template,
            )
        return _render_scene_aware_edit(
            source_uri=source_uri,
            edit_plan=applied_plan,
            staged_dir=staged_dir,
            output_dir=output_dir,
            storage_client=storage_client,
            overlay_timeline=overlay_timeline,
            editorial_template=editorial_template,
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
        )

    staged_source_path = stage_source_asset(
        source_uri=source_uri,
        staged_dir=staged_dir,
        storage_client=storage_client,
    )
    source_probe = probe_media_file(staged_source_path, ffprobe_bin=ffprobe_bin)
    video_filter = build_overlay_video_filter(
        base_filter=_VIDEO_FILTER,
        timeline=overlay_timeline,
        clip_duration_seconds=source_probe.duration_seconds,
    )

    final_video_path = output_dir / FINAL_VIDEO_FILENAME
    _render_final_video(
        input_path=staged_source_path,
        output_path=final_video_path,
        source_has_audio=source_probe.has_audio_track,
        video_filter=video_filter,
        ffmpeg_bin=ffmpeg_bin,
    )

    output_probe = probe_media_file(final_video_path, ffprobe_bin=ffprobe_bin)
    if output_probe.width != TARGET_WIDTH or output_probe.height != TARGET_HEIGHT:
        raise RuntimeError(
            "Basic editor output dimensions were not normalized to "
            f"{TARGET_WIDTH}x{TARGET_HEIGHT}"
        )
    if not output_probe.has_audio_track:
        raise RuntimeError("Basic editor output is missing the required audio track")

    trace_path, trace_payload = _persist_overlay_render_trace(
        output_dir=output_dir,
        base_filter=_VIDEO_FILTER,
        timeline=overlay_timeline,
        clip_duration_seconds=source_probe.duration_seconds,
    )

    cover_artifact = extract_cover_frame(
        video_path=final_video_path,
        output_path=output_dir / FINAL_COVER_FILENAME,
        duration_seconds=output_probe.duration_seconds,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
    )

    return BasicEditorArtifact(
        template_version=PHASE1_TEMPLATE_VERSION,
        source_uri=normalized_source_uri,
        staged_source_path=staged_source_path,
        staged_segment_paths=(staged_source_path,),
        final_video_path=final_video_path,
        cover_image_path=cover_artifact.image_path,
        width=output_probe.width,
        height=output_probe.height,
        duration_seconds=output_probe.duration_seconds,
        cover_frame_timestamp_seconds=cover_artifact.timestamp_seconds,
        source_had_audio_track=source_probe.has_audio_track,
        has_audio_track=output_probe.has_audio_track,
        editorial_template_id=None,
        editorial_template_version=None,
        applied_edit_plan=None,
        overlay_render_trace_path=trace_path,
        overlay_render_trace=trace_payload,
    )


def _render_scene_aware_edit(
    *,
    source_uri: str | Path,
    edit_plan: SceneAwareEditPlan,
    staged_dir: Path,
    output_dir: Path,
    storage_client: ObjectStorageClient | None,
    overlay_timeline: OverlayTimeline | None,
    editorial_template: EditorialTemplate | None,
    ffmpeg_bin: str,
    ffprobe_bin: str,
) -> BasicEditorArtifact:
    normalized_source_uri = _normalize_source_uri(source_uri)
    segment_paths: list[Path] = []
    rendered_segment_paths: list[Path] = []
    for index, segment in enumerate(edit_plan.segments, start=1):
        segment_staged_dir = staged_dir / f"segment-{index:03d}"
        staged_segment_path = stage_source_asset(
            source_uri=segment.source_uri,
            staged_dir=segment_staged_dir,
            storage_client=storage_client,
        )
        source_probe = probe_media_file(staged_segment_path, ffprobe_bin=ffprobe_bin)
        rendered_segment_path = output_dir / f"segment-{index:03d}.mp4"
        _render_timeline_segment(
            input_path=staged_segment_path,
            output_path=rendered_segment_path,
            source_has_audio=source_probe.has_audio_track,
            source_start_seconds=segment.source_start_seconds,
            duration_seconds=segment.duration_seconds,
            ffmpeg_bin=ffmpeg_bin,
        )
        segment_paths.append(staged_segment_path)
        rendered_segment_paths.append(rendered_segment_path)

    combined_source_path = output_dir / "combined_source.mp4"
    _concat_segments(
        segment_paths=rendered_segment_paths,
        output_path=combined_source_path,
        ffmpeg_bin=ffmpeg_bin,
    )
    combined_probe = probe_media_file(combined_source_path, ffprobe_bin=ffprobe_bin)
    video_filter = build_overlay_video_filter(
        base_filter=_VIDEO_FILTER,
        timeline=overlay_timeline,
        clip_duration_seconds=combined_probe.duration_seconds,
    )

    final_video_path = output_dir / FINAL_VIDEO_FILENAME
    _render_final_video(
        input_path=combined_source_path,
        output_path=final_video_path,
        source_has_audio=combined_probe.has_audio_track,
        video_filter=video_filter,
        ffmpeg_bin=ffmpeg_bin,
    )

    output_probe = probe_media_file(final_video_path, ffprobe_bin=ffprobe_bin)
    if output_probe.width != TARGET_WIDTH or output_probe.height != TARGET_HEIGHT:
        raise RuntimeError(
            "Scene-aware editor output dimensions were not normalized to "
            f"{TARGET_WIDTH}x{TARGET_HEIGHT}"
        )
    if not output_probe.has_audio_track:
        raise RuntimeError("Scene-aware editor output is missing the required audio track")

    trace_path, trace_payload = _persist_overlay_render_trace(
        output_dir=output_dir,
        base_filter=_VIDEO_FILTER,
        timeline=overlay_timeline,
        clip_duration_seconds=combined_probe.duration_seconds,
    )

    cover_artifact = extract_cover_frame(
        video_path=final_video_path,
        output_path=output_dir / FINAL_COVER_FILENAME,
        duration_seconds=output_probe.duration_seconds,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
    )

    return BasicEditorArtifact(
        template_version=PHASE1_TEMPLATE_VERSION,
        source_uri=normalized_source_uri,
        staged_source_path=segment_paths[0],
        staged_segment_paths=tuple(segment_paths),
        final_video_path=final_video_path,
        cover_image_path=cover_artifact.image_path,
        width=output_probe.width,
        height=output_probe.height,
        duration_seconds=output_probe.duration_seconds,
        cover_frame_timestamp_seconds=cover_artifact.timestamp_seconds,
        source_had_audio_track=combined_probe.has_audio_track,
        has_audio_track=output_probe.has_audio_track,
        editorial_template_id=(
            editorial_template.template_id if editorial_template is not None else None
        ),
        editorial_template_version=(
            editorial_template.template_version if editorial_template is not None else None
        ),
        applied_edit_plan=edit_plan,
        overlay_render_trace_path=trace_path,
        overlay_render_trace=trace_payload,
    )


def stage_source_asset(
    *,
    source_uri: str | Path,
    staged_dir: str | Path,
    storage_client: ObjectStorageClient | None = None,
) -> Path:
    """Copy a local source or download an S3 object into a stable local path."""

    normalized_source_uri = _normalize_source_uri(source_uri)
    resolved_staged_dir = Path(staged_dir)
    resolved_staged_dir.mkdir(parents=True, exist_ok=True)

    local_source_path = _resolve_local_source_path(source_uri)
    if local_source_path is not None:
        suffix = local_source_path.suffix or ".mp4"
        staged_path = resolved_staged_dir / f"source{suffix.lower()}"
        shutil.copyfile(local_source_path, staged_path)
        return staged_path

    if not normalized_source_uri.startswith("s3://"):
        raise ValueError(f"Unsupported source URI: {normalized_source_uri}")
    if storage_client is None:
        raise ValueError("storage_client is required to stage s3:// sources")

    retrieved = storage_client.get_object(storage_uri=normalized_source_uri)
    suffix = _storage_object_suffix(
        storage_uri=normalized_source_uri,
        content_type=retrieved.content_type,
    )
    staged_path = resolved_staged_dir / f"source{suffix}"
    staged_path.write_bytes(retrieved.body)
    return staged_path


def probe_media_file(path: str | Path, *, ffprobe_bin: str = "ffprobe") -> MediaProbe:
    """Probe width, height, duration, and audio presence for a media file."""

    resolved_path = Path(path)
    completed = _run_command(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(resolved_path),
        ],
        failure_prefix=f"Failed to probe media file {resolved_path}",
    )
    payload = json.loads(completed.stdout)
    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        raise RuntimeError("ffprobe returned invalid stream metadata")

    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if video_stream is None:
        raise RuntimeError(f"Media file {resolved_path} does not contain a video stream")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    format_payload = payload.get("format", {})
    duration_raw = None
    if isinstance(video_stream, dict):
        duration_raw = video_stream.get("duration")
    if duration_raw in (None, "") and isinstance(format_payload, dict):
        duration_raw = format_payload.get("duration")

    duration_seconds = float(duration_raw or 0.0)
    has_audio_track = any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams
    )
    return MediaProbe(
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        has_audio_track=has_audio_track,
    )


def _render_timeline_segment(
    *,
    input_path: Path,
    output_path: Path,
    source_has_audio: bool,
    source_start_seconds: float,
    duration_seconds: float,
    ffmpeg_bin: str,
) -> None:
    command = [
        ffmpeg_bin,
        "-y",
    ]
    if source_start_seconds > 0:
        command.extend(["-ss", f"{source_start_seconds:.3f}"])
    command.extend(
        [
            "-i",
            str(input_path),
        ]
    )
    if not source_has_audio:
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                (
                    "anullsrc="
                    f"channel_layout={_AUDIO_CHANNEL_LAYOUT}:sample_rate={_AUDIO_SAMPLE_RATE}"
                ),
            ]
        )

    command.extend(
        [
            "-t",
            f"{duration_seconds:.3f}",
            "-map_metadata",
            "-1",
            "-filter:v",
            _VIDEO_FILTER,
            "-map",
            "0:v:0",
        ]
    )
    if source_has_audio:
        command.extend(["-map", "0:a:0"])
    else:
        command.extend(["-map", "1:a:0", "-shortest"])

    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-ar",
            str(_AUDIO_SAMPLE_RATE),
            "-movflags",
            "+faststart",
            "-threads",
            "1",
            str(output_path),
        ]
    )
    _run_command(command, failure_prefix=f"Failed to render edit segment for {input_path}")


def _concat_segments(
    *,
    segment_paths: list[Path],
    output_path: Path,
    ffmpeg_bin: str,
) -> None:
    concat_file = output_path.with_suffix(".concat.txt")
    concat_file.write_text(
        "\n".join(f"file '{_ffmpeg_concat_path(path)}'" for path in segment_paths) + "\n",
        encoding="utf-8",
    )
    _run_command(
        [
            ffmpeg_bin,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ],
        failure_prefix="Failed to concatenate scene edit segments",
    )


def _render_final_video(
    *,
    input_path: Path,
    output_path: Path,
    source_has_audio: bool,
    video_filter: str,
    ffmpeg_bin: str,
) -> None:
    command = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
    ]
    if not source_has_audio:
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                (
                    "anullsrc="
                    f"channel_layout={_AUDIO_CHANNEL_LAYOUT}:sample_rate={_AUDIO_SAMPLE_RATE}"
                ),
            ]
        )

    command.extend(
        [
            "-map_metadata",
            "-1",
            "-filter:v",
            video_filter,
            "-map",
            "0:v:0",
        ]
    )
    if source_has_audio:
        command.extend(["-map", "0:a:0"])
    else:
        command.extend(["-map", "1:a:0", "-shortest"])

    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-ar",
            str(_AUDIO_SAMPLE_RATE),
            "-movflags",
            "+faststart",
            "-threads",
            "1",
            str(output_path),
        ]
    )

    _run_command(command, failure_prefix=f"Failed to render basic editor output for {input_path}")


def _normalize_source_uri(source_uri: str | Path) -> str:
    if isinstance(source_uri, Path):
        return str(source_uri.resolve())
    normalized = str(source_uri).strip()
    if not normalized:
        raise ValueError("source_uri must not be blank")
    return normalized


def _resolve_local_source_path(source_uri: str | Path) -> Path | None:
    if isinstance(source_uri, Path):
        return source_uri.resolve()

    normalized = str(source_uri).strip()
    if normalized.startswith("file://"):
        parsed = urlparse(normalized)
        return Path(parsed.path).resolve()
    if normalized.startswith("s3://"):
        return None

    candidate = Path(normalized)
    if candidate.exists():
        return candidate.resolve()
    return None


def _storage_object_suffix(*, storage_uri: str, content_type: str | None) -> str:
    parsed = urlparse(storage_uri)
    suffix = Path(parsed.path).suffix.lower()
    if suffix:
        return suffix
    if content_type is not None:
        normalized_content_type = content_type.strip().lower()
        if normalized_content_type in _CONTENT_TYPE_EXTENSIONS:
            return _CONTENT_TYPE_EXTENSIONS[normalized_content_type]
    return ".mp4"


def _ffmpeg_concat_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "'\\''")


def _run_command(command: list[str], *, failure_prefix: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        details = stderr or stdout or "no output captured"
        raise RuntimeError(f"{failure_prefix}: {details}")
    return completed


__all__ = [
    "BasicEditorArtifact",
    "FINAL_COVER_FILENAME",
    "FINAL_VIDEO_FILENAME",
    "MediaProbe",
    "ObjectStorageClient",
    "PHASE1_TEMPLATE_VERSION",
    "RetrievedStorageObject",
    "TARGET_HEIGHT",
    "TARGET_WIDTH",
    "probe_media_file",
    "render_basic_vertical_edit",
    "stage_source_asset",
]
