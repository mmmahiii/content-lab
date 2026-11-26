"""Deterministic phase-1 single-clip editor backed by FFmpeg."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from content_lab_editing.cover import DEFAULT_COVER_FILENAME, extract_cover_frame
from content_lab_editing.edit_plan import SceneAwareEditPlan
from content_lab_editing.music import MusicBed
from content_lab_editing.overlays import (
    OverlayTimeline,
    TextOverlay,
    build_overlay_render_report,
    build_overlay_safe_area_report,
    build_overlay_video_filter,
    build_rendered_overlay_manifest,
    normalize_overlay_timeline,
)
from content_lab_editing.soundtrack import soundtrack_filter
from content_lab_editing.templates import (
    EditorialTemplate,
    apply_editorial_template,
    overlay_transition_settings,
)
from content_lab_editing.timeline_validation import validate_overlay_timeline_before_render
from content_lab_editing.types import RenderedOverlayManifest
from content_lab_editing.voiceover import MOCK_VOICEOVER_TAG, VoiceoverTrack

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
FINAL_VIDEO_FILENAME = "final_video.mp4"
FINAL_COVER_FILENAME = DEFAULT_COVER_FILENAME
OVERLAY_RENDER_TRACE_FILENAME = "overlay_render_trace.json"
PHASE1_TEMPLATE_VERSION = "basic_vertical_v1"
_AUDIO_CHANNEL_LAYOUT = "stereo"
_AUDIO_SAMPLE_RATE = 48_000
_AUDIO_FADE_IN_SECONDS = 0.12
_AUDIO_FADE_OUT_SECONDS = 0.18
# Clip audio (Runway ambience, if any) sits ~12 dB under the voiceover.
_CLIP_AUDIO_UNDER_VOICE_GAIN = 0.25
_VIDEO_FILTER = (
    f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,"
    f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
    "setsar=1"
)
_DURATION_TOLERANCE_SECONDS = 0.25
# Final encode: "fast" is ~2x quicker than the old "medium" at the same CRF 18 (slightly larger
# files). Override with CONTENT_LAB_X264_PRESET (e.g. "medium" or "slow" for smaller files).
_DEFAULT_FINAL_X264_PRESET = "fast"
_X264_PRESETS = frozenset(
    {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
)
# Chained clips dissolve into each other instead of hard-cutting (0 = hard cuts).
DEFAULT_CLIP_CROSSFADE_SECONDS = 0.3
_INTERMEDIATE_X264_PRESET = "ultrafast"
_INTERMEDIATE_X264_CRF = "12"
_DEFAULT_COMPOSED_FPS = 24.0
_MAX_COMPOSED_PLACEMENTS = 64
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
    audio_duration_seconds: float | None = None
    fps: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None


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
    source_duration_seconds: float
    has_audio_track: bool
    audio_duration_seconds: float | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    rendered_overlay_manifest: RenderedOverlayManifest
    overlay_render_trace_path: Path
    overlay_render_trace: dict[str, Any] | None = None
    editorial_template_id: str | None = None
    editorial_template_version: str | None = None
    applied_edit_plan: SceneAwareEditPlan | None = None
    overlay_render_report: dict[str, Any] | None = None
    overlay_safe_area: dict[str, object] | None = None
    overlay_manifest: tuple[TextOverlay, ...] = ()
    edit_mode: str = "single_clip"
    voiceover: dict[str, Any] | None = None
    music: dict[str, Any] | None = None
    source_composition: dict[str, Any] | None = None


def render_basic_vertical_edit(
    *,
    source_uri: str | Path,
    workdir: str | Path,
    storage_client: ObjectStorageClient | None = None,
    overlay_timeline: OverlayTimeline | None = None,
    scene_plan_for_overlay_diagnostics: Mapping[str, Any] | None = None,
    edit_plan: SceneAwareEditPlan | None = None,
    editorial_template: EditorialTemplate | None = None,
    expected_timeline_duration_seconds: float | None = None,
    voiceover: VoiceoverTrack | None = None,
    music: MusicBed | None = None,
    additional_source_uris: Sequence[str | Path] = (),
    allow_loop: bool = False,
    clip_crossfade_seconds: float = DEFAULT_CLIP_CROSSFADE_SECONDS,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> BasicEditorArtifact:
    """Stage the source clip(s) and export a phase-1 vertical MP4 locally.

    With ``additional_source_uris`` the clips are chained in order and cut to
    ``expected_timeline_duration_seconds``. Media shorter than the timeline is rejected
    (MED-009: never stretch a plan over too little footage) unless ``allow_loop`` is set, in
    which case the sequence repeats from the first clip until the timeline is filled; a single
    clip that does not match is likewise only looped/trimmed with ``allow_loop``. See
    :func:`_compose_source_clips`. ``voiceover`` (see :mod:`content_lab_editing.voiceover`) is
    mixed over the clip audio.
    """

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
            scene_plan_for_overlay_diagnostics=scene_plan_for_overlay_diagnostics,
            editorial_template=editorial_template,
            voiceover=voiceover,
            music=music,
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
        )

    staged_source_path = stage_source_asset(
        source_uri=source_uri,
        staged_dir=staged_dir,
        storage_client=storage_client,
    )
    source_probe = probe_media_file(staged_source_path, ffprobe_bin=ffprobe_bin)
    source_composition: dict[str, Any] | None = None
    staged_paths: tuple[Path, ...] = (staged_source_path,)
    needs_composition = bool(additional_source_uris) or (
        allow_loop
        and expected_timeline_duration_seconds is not None
        and abs(source_probe.duration_seconds - float(expected_timeline_duration_seconds))
        > _DURATION_TOLERANCE_SECONDS
    )
    if needs_composition:
        staged_source_path, source_probe, source_composition, staged_paths = _compose_source_clips(
            primary_path=staged_source_path,
            primary_probe=source_probe,
            additional_source_uris=additional_source_uris,
            target_duration_seconds=expected_timeline_duration_seconds,
            allow_loop=allow_loop,
            crossfade_seconds=clip_crossfade_seconds,
            staged_dir=staged_dir,
            output_dir=output_dir,
            storage_client=storage_client,
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
        )
    _validate_expected_timeline_duration(
        actual_seconds=source_probe.duration_seconds,
        expected_seconds=expected_timeline_duration_seconds,
    )
    overlay_transition = (
        overlay_transition_settings(editorial_template) if editorial_template is not None else None
    )
    normalized_overlays = normalize_overlay_timeline(
        overlay_timeline,
        clip_duration_seconds=source_probe.duration_seconds,
        frame_width=TARGET_WIDTH,
        frame_height=TARGET_HEIGHT,
        transition=overlay_transition,
    )
    validate_overlay_timeline_before_render(
        normalized_overlays,
        clip_duration_seconds=source_probe.duration_seconds,
        transition=overlay_transition,
    )
    video_filter = build_overlay_video_filter(
        base_filter=_VIDEO_FILTER,
        normalized_timeline=normalized_overlays,
        frame_width=TARGET_WIDTH,
        frame_height=TARGET_HEIGHT,
        transition=overlay_transition,
    )
    overlay_safe_area = build_overlay_safe_area_report(
        overlay_timeline,
        clip_duration_seconds=source_probe.duration_seconds,
        frame_width=TARGET_WIDTH,
        frame_height=TARGET_HEIGHT,
    )

    overlay_render_report = build_overlay_render_report(
        timeline=overlay_timeline,
        clip_duration_seconds=source_probe.duration_seconds,
        scene_plan=scene_plan_for_overlay_diagnostics,
    )

    rendered_manifest = build_rendered_overlay_manifest(
        timeline=overlay_timeline,
        clip_duration_seconds=float(source_probe.duration_seconds),
        frame_width_px=TARGET_WIDTH,
        frame_height_px=TARGET_HEIGHT,
    )

    overlay_render_trace_path = output_dir / OVERLAY_RENDER_TRACE_FILENAME

    final_video_path = output_dir / FINAL_VIDEO_FILENAME
    _render_final_video(
        input_path=staged_source_path,
        output_path=final_video_path,
        source_has_audio=source_probe.has_audio_track,
        target_duration_seconds=source_probe.duration_seconds,
        video_filter=video_filter,
        voiceover=voiceover,
        music=music,
        ffmpeg_bin=ffmpeg_bin,
    )

    output_probe = probe_media_file(final_video_path, ffprobe_bin=ffprobe_bin)
    if output_probe.width != TARGET_WIDTH or output_probe.height != TARGET_HEIGHT:
        raise RuntimeError(
            "Basic editor output dimensions were not normalized to "
            f"{TARGET_WIDTH}x{TARGET_HEIGHT}"
        )
    _validate_audio_sync(probe=output_probe)

    overlay_render_trace = _overlay_trace_payload(
        rendered_manifest,
        edit_mode="single_clip" if source_composition is None else "multi_clip",
    )
    overlay_render_trace_path.write_text(
        json.dumps(overlay_render_trace, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
        staged_segment_paths=staged_paths,
        final_video_path=final_video_path,
        cover_image_path=cover_artifact.image_path,
        width=output_probe.width,
        height=output_probe.height,
        duration_seconds=output_probe.duration_seconds,
        cover_frame_timestamp_seconds=cover_artifact.timestamp_seconds,
        source_had_audio_track=source_probe.has_audio_track,
        source_duration_seconds=source_probe.duration_seconds,
        has_audio_track=output_probe.has_audio_track,
        audio_duration_seconds=output_probe.audio_duration_seconds,
        fps=output_probe.fps,
        video_codec=output_probe.video_codec,
        audio_codec=output_probe.audio_codec,
        rendered_overlay_manifest=rendered_manifest,
        overlay_render_trace_path=overlay_render_trace_path,
        overlay_render_trace=overlay_render_trace,
        editorial_template_id=None,
        editorial_template_version=None,
        applied_edit_plan=None,
        overlay_render_report=overlay_render_report,
        overlay_safe_area=overlay_safe_area,
        overlay_manifest=normalized_overlays,
        edit_mode="single_clip" if source_composition is None else "multi_clip",
        voiceover=voiceover.as_dict() if voiceover is not None else None,
        music=music.as_dict() if music is not None else None,
        source_composition=source_composition,
    )


def _render_scene_aware_edit(
    *,
    source_uri: str | Path,
    edit_plan: SceneAwareEditPlan,
    staged_dir: Path,
    output_dir: Path,
    storage_client: ObjectStorageClient | None,
    overlay_timeline: OverlayTimeline | None,
    scene_plan_for_overlay_diagnostics: Mapping[str, Any] | None,
    editorial_template: EditorialTemplate | None,
    ffmpeg_bin: str,
    ffprobe_bin: str,
    voiceover: VoiceoverTrack | None = None,
    music: MusicBed | None = None,
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
        _validate_scene_segment_source_coverage(
            scene_id=segment.scene_id,
            source_duration_seconds=source_probe.duration_seconds,
            source_start_seconds=segment.source_start_seconds,
            required_duration_seconds=segment.duration_seconds,
        )
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
    _validate_scene_plan_vs_available_media(
        expected_scene_duration_seconds=edit_plan.duration_seconds,
        available_media_duration_seconds=combined_probe.duration_seconds,
    )
    overlay_transition = (
        overlay_transition_settings(editorial_template) if editorial_template is not None else None
    )
    normalized_overlays = normalize_overlay_timeline(
        overlay_timeline,
        clip_duration_seconds=combined_probe.duration_seconds,
        frame_width=TARGET_WIDTH,
        frame_height=TARGET_HEIGHT,
        transition=overlay_transition,
    )
    validate_overlay_timeline_before_render(
        normalized_overlays,
        clip_duration_seconds=combined_probe.duration_seconds,
        transition=overlay_transition,
    )
    video_filter = build_overlay_video_filter(
        base_filter=_VIDEO_FILTER,
        normalized_timeline=normalized_overlays,
        frame_width=TARGET_WIDTH,
        frame_height=TARGET_HEIGHT,
        transition=overlay_transition,
    )
    overlay_safe_area = build_overlay_safe_area_report(
        overlay_timeline,
        clip_duration_seconds=combined_probe.duration_seconds,
        frame_width=TARGET_WIDTH,
        frame_height=TARGET_HEIGHT,
    )

    overlay_render_report = build_overlay_render_report(
        timeline=overlay_timeline,
        clip_duration_seconds=combined_probe.duration_seconds,
        scene_plan=scene_plan_for_overlay_diagnostics,
    )

    rendered_manifest = build_rendered_overlay_manifest(
        timeline=overlay_timeline,
        clip_duration_seconds=float(combined_probe.duration_seconds),
        frame_width_px=TARGET_WIDTH,
        frame_height_px=TARGET_HEIGHT,
    )

    overlay_render_trace_path = output_dir / OVERLAY_RENDER_TRACE_FILENAME

    final_video_path = output_dir / FINAL_VIDEO_FILENAME
    _render_final_video(
        input_path=combined_source_path,
        output_path=final_video_path,
        source_has_audio=combined_probe.has_audio_track,
        target_duration_seconds=combined_probe.duration_seconds,
        video_filter=video_filter,
        voiceover=voiceover,
        music=music,
        ffmpeg_bin=ffmpeg_bin,
    )

    output_probe = probe_media_file(final_video_path, ffprobe_bin=ffprobe_bin)
    if output_probe.width != TARGET_WIDTH or output_probe.height != TARGET_HEIGHT:
        raise RuntimeError(
            "Scene-aware editor output dimensions were not normalized to "
            f"{TARGET_WIDTH}x{TARGET_HEIGHT}"
        )
    _validate_audio_sync(probe=output_probe)

    overlay_render_trace = _overlay_trace_payload(rendered_manifest, edit_mode="scene_composed")
    overlay_render_trace_path.write_text(
        json.dumps(overlay_render_trace, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
        source_duration_seconds=combined_probe.duration_seconds,
        has_audio_track=output_probe.has_audio_track,
        audio_duration_seconds=output_probe.audio_duration_seconds,
        fps=output_probe.fps,
        video_codec=output_probe.video_codec,
        audio_codec=output_probe.audio_codec,
        rendered_overlay_manifest=rendered_manifest,
        overlay_render_trace_path=overlay_render_trace_path,
        overlay_render_trace=overlay_render_trace,
        editorial_template_id=(
            editorial_template.template_id if editorial_template is not None else None
        ),
        editorial_template_version=(
            editorial_template.template_version if editorial_template is not None else None
        ),
        applied_edit_plan=edit_plan,
        overlay_render_report=overlay_render_report,
        overlay_safe_area=overlay_safe_area,
        overlay_manifest=normalized_overlays,
        edit_mode="scene_composed",
        voiceover=voiceover.as_dict() if voiceover is not None else None,
        music=music.as_dict() if music is not None else None,
    )


def _compose_source_clips(
    *,
    primary_path: Path,
    primary_probe: MediaProbe,
    additional_source_uris: Sequence[str | Path],
    target_duration_seconds: float | None,
    staged_dir: Path,
    output_dir: Path,
    storage_client: ObjectStorageClient | None,
    ffmpeg_bin: str,
    ffprobe_bin: str,
    allow_loop: bool = False,
    crossfade_seconds: float = 0.0,
) -> tuple[Path, MediaProbe, dict[str, Any], tuple[Path, ...]]:
    """Chain clips (looping from the first) into one normalized source of the target length.

    A single provider clip is at most 10 s, so longer reels need several clips or a loop.
    Clips play in order; if they run out before the target, the sequence starts again from the
    first clip; the last placement is cut to land exactly on the target. Every placement is
    re-encoded to 1080x1920 at one frame rate so the pieces concatenate without re-timing.
    """

    clips: list[tuple[Path, MediaProbe, str]] = [(primary_path, primary_probe, str(primary_path))]
    for index, uri in enumerate(additional_source_uris, start=2):
        staged = stage_source_asset(
            source_uri=uri,
            staged_dir=staged_dir / f"clip-{index:03d}",
            storage_client=storage_client,
        )
        clips.append((staged, probe_media_file(staged, ffprobe_bin=ffprobe_bin), str(uri)))
    for path, probe, _ in clips:
        if probe.duration_seconds <= 0:
            raise ValueError(f"Source clip {path} has no duration")
    target = (
        float(target_duration_seconds)
        if target_duration_seconds is not None
        else sum(probe.duration_seconds for _, probe, _ in clips)
    )
    if target <= 0:
        raise ValueError("Composed source target duration must be positive")
    available = sum(probe.duration_seconds for _, probe, _ in clips)
    if not allow_loop and available + _DURATION_TOLERANCE_SECONDS < target:
        raise ValueError(
            "Source media duration does not match expected timeline duration: "
            f"{available:.3f}s of clips for a {target:.3f}s timeline (looping not allowed)"
        )
    fps = primary_probe.fps or _DEFAULT_COMPOSED_FPS
    placements: list[dict[str, Any]] = []
    rendered: list[Path] = []
    cursor = 0.0
    while target - cursor > 1e-3:
        if len(placements) >= _MAX_COMPOSED_PLACEMENTS:
            raise ValueError("Source clips are too short to fill the timeline")
        clip_index = len(placements) % len(clips)
        path, probe, uri = clips[clip_index]
        length = min(probe.duration_seconds, target - cursor)
        if not allow_loop and len(placements) == len(clips) - 1:
            # Last clip absorbs sub-tolerance rounding instead of a sliver of a loop.
            length = target - cursor
        piece = output_dir / f"composed-{len(placements) + 1:03d}.mp4"
        _render_timeline_segment(
            input_path=path,
            output_path=piece,
            source_has_audio=probe.has_audio_track,
            source_start_seconds=0.0,
            duration_seconds=length,
            fps=fps,
            ffmpeg_bin=ffmpeg_bin,
        )
        placements.append(
            {
                "clip_index": clip_index,
                "source_uri": uri,
                "timeline_start_seconds": round(cursor, 3),
                "timeline_end_seconds": round(cursor + length, 3),
                "looped": len(placements) >= len(clips),
            }
        )
        rendered.append(piece)
        cursor += length
    combined = output_dir / "composed_source.mp4"
    lengths = [p["timeline_end_seconds"] - p["timeline_start_seconds"] for p in placements]
    fade = min(crossfade_seconds, *(length / 4 for length in lengths)) if len(rendered) > 1 else 0
    if fade > 0.01:
        _crossfade_segments(
            segment_paths=rendered,
            lengths=lengths,
            crossfade_seconds=fade,
            output_path=combined,
            ffmpeg_bin=ffmpeg_bin,
        )
    else:
        fade = 0.0
        _concat_segments(segment_paths=rendered, output_path=combined, ffmpeg_bin=ffmpeg_bin)
    combined_probe = probe_media_file(combined, ffprobe_bin=ffprobe_bin)
    loops = max(len(placements) - len(clips), 0)
    composition = {
        "mode": "loop" if loops else ("trim" if len(clips) == 1 else "chain"),
        "target_duration_seconds": round(target, 3),
        "composed_duration_seconds": round(combined_probe.duration_seconds, 3),
        "clips": [
            {
                "clip_index": i,
                "source_uri": uri,
                "duration_seconds": round(probe.duration_seconds, 3),
            }
            for i, (_, probe, uri) in enumerate(clips)
        ],
        "placements": placements,
        "looped_placements": loops,
        "crossfade_seconds": round(fade, 3),
    }
    return combined, combined_probe, composition, tuple(path for path, _, _ in clips)


def _overlay_trace_payload(manifest: RenderedOverlayManifest, *, edit_mode: str) -> dict[str, Any]:
    payload = manifest.as_json_dict()
    payload["artifact_type"] = "overlay_render_trace"
    payload["overlay_count"] = len(manifest.overlays)
    payload["edit_mode"] = edit_mode
    return payload


def _validate_expected_timeline_duration(
    *,
    actual_seconds: float,
    expected_seconds: float | None,
) -> None:
    if expected_seconds is None:
        return
    if abs(float(actual_seconds) - float(expected_seconds)) > 0.25:
        raise ValueError(
            "Source media duration does not match expected timeline duration: "
            f"{actual_seconds:.3f}s vs {float(expected_seconds):.3f}s"
        )


def _validate_scene_segment_source_coverage(
    *,
    scene_id: str,
    source_duration_seconds: float,
    source_start_seconds: float,
    required_duration_seconds: float,
) -> None:
    available_seconds = max(float(source_duration_seconds) - float(source_start_seconds), 0.0)
    required_seconds = float(required_duration_seconds)
    if available_seconds + 1e-6 < required_seconds:
        raise ValueError(
            "Scene segment source media is shorter than planned duration; "
            "rebuild scene plan or provide a longer asset "
            f"(scene_id={scene_id}, available={available_seconds:.3f}s, required={required_seconds:.3f}s)"
        )


def _validate_scene_plan_vs_available_media(
    *,
    expected_scene_duration_seconds: float,
    available_media_duration_seconds: float,
    tolerance_seconds: float = 0.25,
) -> None:
    expected = float(expected_scene_duration_seconds)
    available = float(available_media_duration_seconds)
    if abs(expected - available) > tolerance_seconds:
        raise ValueError(
            "Scene plan duration does not match available stitched media duration; "
            "refusing to squeeze scene timings "
            f"(expected={expected:.3f}s, available={available:.3f}s, tolerance={tolerance_seconds:.3f}s)"
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
    fps = _parse_frame_rate(video_stream.get("avg_frame_rate"))
    video_codec = _optional_text(video_stream.get("codec_name"))
    format_payload = payload.get("format", {})
    duration_raw = None
    if isinstance(video_stream, dict):
        duration_raw = video_stream.get("duration")
    if duration_raw in (None, "") and isinstance(format_payload, dict):
        duration_raw = format_payload.get("duration")

    duration_seconds = float(duration_raw or 0.0)
    audio_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ),
        None,
    )
    has_audio_track = audio_stream is not None
    audio_duration_seconds: float | None = None
    audio_codec: str | None = None
    if isinstance(audio_stream, dict):
        audio_codec = _optional_text(audio_stream.get("codec_name"))
        audio_duration_raw = audio_stream.get("duration")
        if audio_duration_raw in (None, "", "N/A"):
            audio_duration_raw = format_payload.get("duration")
        audio_duration_seconds = float(audio_duration_raw) if audio_duration_raw else None
    return MediaProbe(
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        has_audio_track=has_audio_track,
        audio_duration_seconds=audio_duration_seconds,
        fps=fps,
        video_codec=video_codec,
        audio_codec=audio_codec,
    )


def _parse_frame_rate(value: object) -> float | None:
    if value in (None, "", "0/0", "N/A"):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    if "/" in value:
        numerator, denominator = value.split("/", maxsplit=1)
        try:
            denom = float(denominator)
            if denom == 0:
                return None
            return float(numerator) / denom
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _render_timeline_segment(
    *,
    input_path: Path,
    output_path: Path,
    source_has_audio: bool,
    source_start_seconds: float,
    duration_seconds: float,
    ffmpeg_bin: str,
    fps: float | None = None,
) -> None:
    video_filter = _VIDEO_FILTER if fps is None else f"{_VIDEO_FILTER},fps={fps:.6g}"
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
            # Intermediate: re-encoded again by the final render, so near-lossless and fast.
            "-preset",
            _INTERMEDIATE_X264_PRESET,
            "-crf",
            _INTERMEDIATE_X264_CRF,
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
            "0",
            str(output_path),
        ]
    )
    _run_command(command, failure_prefix=f"Failed to render edit segment for {input_path}")


def _crossfade_segments(
    *,
    segment_paths: list[Path],
    lengths: list[float],
    crossfade_seconds: float,
    output_path: Path,
    ffmpeg_bin: str,
) -> None:
    """Join pieces with video dissolves while keeping the exact total length.

    Every piece but the last is extended by holding its final frame for ``crossfade_seconds``;
    the next piece fades in over that hold. No footage is lost and the timeline length is the
    sum of the pieces, so overlay and voice timing are unaffected. Audio is concatenated as is.
    """

    count = len(segment_paths)
    inputs: list[str] = []
    for path in segment_paths:
        inputs += ["-i", str(path)]
    parts: list[str] = []
    for index in range(count):
        if index < count - 1:
            parts.append(
                f"[{index}:v]tpad=stop_mode=clone:stop_duration={crossfade_seconds:.3f},"
                f"settb=AVTB[v{index}]"
            )
        else:
            parts.append(f"[{index}:v]settb=AVTB[v{index}]")
    previous = "v0"
    offset = 0.0
    for index in range(1, count):
        offset += lengths[index - 1]
        label = f"x{index}"
        parts.append(
            f"[{previous}][v{index}]xfade=transition=fade:duration={crossfade_seconds:.3f}:"
            f"offset={offset:.3f}[{label}]"
        )
        previous = label
    audio_inputs = "".join(f"[{index}:a]" for index in range(count))
    parts.append(f"{audio_inputs}concat=n={count}:v=0:a=1[aout]")
    _run_command(
        [
            ffmpeg_bin,
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(parts),
            "-map",
            f"[{previous}]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            _INTERMEDIATE_X264_PRESET,
            "-crf",
            _INTERMEDIATE_X264_CRF,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-ar",
            str(_AUDIO_SAMPLE_RATE),
            "-threads",
            "0",
            str(output_path),
        ],
        failure_prefix="Failed to crossfade source clips",
    )


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
    target_duration_seconds: float,
    video_filter: str,
    ffmpeg_bin: str,
    voiceover: VoiceoverTrack | None = None,
    music: MusicBed | None = None,
) -> None:
    fade_in_s, fade_out_s = _resolved_audio_fades(target_duration_seconds)
    fade_out_start = max(float(target_duration_seconds) - fade_out_s, 0.0)
    duration = f"{target_duration_seconds:.3f}"
    command = [ffmpeg_bin, "-y", "-i", str(input_path)]
    if source_has_audio:
        bed = f"[0:a:0]apad,atrim=0:{duration}"
    else:
        command += [
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout={_AUDIO_CHANNEL_LAYOUT}:sample_rate={_AUDIO_SAMPLE_RATE}",
        ]
        bed = f"[1:a:0]atrim=0:{duration}"
    master = (
        f"afade=t=in:st=0:d={fade_in_s:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out_s:.3f},"
        "asetpts=N/SR/TB[aout]"
    )
    next_index = 1 if source_has_audio else 2
    voice_index = music_index = None
    if voiceover is not None:
        voice_index = next_index
        command += ["-i", str(voiceover.path)]
        next_index += 1
    if music is not None:
        music_index = next_index
        command += ["-i", str(music.path)]
    soundtrack = soundtrack_filter(
        voice_index=voice_index,
        music_index=music_index,
        duration_seconds=float(target_duration_seconds),
        output_label="soundtrack",
    )
    if soundtrack is None:
        audio_graph = f"{bed},{master}"
    else:
        audio_graph = (
            f"{bed},volume={_CLIP_AUDIO_UNDER_VOICE_GAIN}[bed];{soundtrack};"
            f"[bed][soundtrack]amix=inputs=2:duration=first:normalize=0,{master}"
        )
    command += [
        "-filter_complex",
        f"[0:v:0]{video_filter}[vout];{audio_graph}",
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-map_metadata",
        "-1",
    ]
    if voiceover is not None and voiceover.is_mock:
        # Lets QA tell a mock tone from real speech by looking at the file alone.
        command += ["-metadata", f"comment={MOCK_VOICEOVER_TAG}"]
    command += [
        "-c:v",
        "libx264",
        "-preset",
        _final_x264_preset(),
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
        # All cores: x264 output is still deterministic for a given machine/thread count.
        "-threads",
        "0",
        "-shortest",
        str(output_path),
    ]

    _run_command(command, failure_prefix=f"Failed to render basic editor output for {input_path}")


def _final_x264_preset() -> str:
    value = os.environ.get("CONTENT_LAB_X264_PRESET", "").strip().lower()
    if not value:
        return _DEFAULT_FINAL_X264_PRESET
    if value not in _X264_PRESETS:
        raise ValueError(f"CONTENT_LAB_X264_PRESET={value!r} is not an x264 preset")
    return value


def _resolved_audio_fades(target_duration_seconds: float) -> tuple[float, float]:
    span = max(float(target_duration_seconds), 0.0)
    if span <= 0.0:
        return (0.0, 0.0)
    fade_in = min(_AUDIO_FADE_IN_SECONDS, span / 2.0)
    fade_out = min(_AUDIO_FADE_OUT_SECONDS, span / 2.0)
    if fade_in + fade_out > span:
        scale = span / (fade_in + fade_out)
        fade_in *= scale
        fade_out *= scale
    return (fade_in, fade_out)


def _validate_audio_sync(
    *,
    probe: MediaProbe,
    tolerance_seconds: float = 0.25,
) -> None:
    if not probe.has_audio_track:
        raise RuntimeError("Rendered output is missing audio track")
    if probe.audio_duration_seconds is None:
        raise RuntimeError("Rendered output audio duration is unavailable")
    drift = abs(float(probe.audio_duration_seconds) - float(probe.duration_seconds))
    if drift > tolerance_seconds:
        raise RuntimeError(
            "Rendered output audio/video drift exceeds tolerance: "
            f"audio={probe.audio_duration_seconds:.3f}s video={probe.duration_seconds:.3f}s "
            f"drift={drift:.3f}s tolerance={tolerance_seconds:.3f}s"
        )


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
    "OVERLAY_RENDER_TRACE_FILENAME",
]
