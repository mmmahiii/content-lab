from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content_lab_editing.media_timeline import build_timeline_render_trace
from content_lab_editing.package_builder import build_package_directory

_TIMELINE = {
    "version": "med-001.v1",
    "timeline_id": "timeline-test",
    "duration_seconds": 12.0,
    "cover_frame_timestamp_seconds": 0.5,
    "source_clips": [{"clip_id": "source-001", "duration_seconds": 12.0}],
    "scenes": [{"scene_id": "scene-001", "start_seconds": 0.0, "end_seconds": 12.0}],
    "edit_segments": [
        {
            "segment_id": "segment-001",
            "timeline_start_seconds": 0.0,
            "timeline_end_seconds": 12.0,
            "source_clip_id": "source-001",
            "source_start_seconds": 0.0,
            "source_end_seconds": 12.0,
        }
    ],
    "overlays": [
        {"overlay_id": "overlay-001", "start_seconds": 0.0, "end_seconds": 4.0, "text": "Hook"}
    ],
    "audio_tracks": [
        {
            "track_id": "audio-master",
            "role": "master",
            "start_seconds": 0.0,
            "end_seconds": 12.0,
            "fade_in_seconds": 0.12,
            "fade_out_seconds": 0.18,
        }
    ],
}


def _trace(
    *,
    canonical_timeline: Mapping[str, Any] = _TIMELINE,
    final_video_duration_seconds: float = 12.0,
    final_video_has_audio_stream: bool = True,
    final_audio_duration_seconds: float | None = 12.0,
    source_asset_duration_seconds: float | None = 12.0,
    creative_duration_seconds: float | None = 12.0,
    editing_duration_seconds: float | None = 12.0,
    cover_timestamp_seconds: float | None = 0.5,
) -> dict[str, Any]:
    return build_timeline_render_trace(
        canonical_timeline=canonical_timeline,
        final_video_duration_seconds=final_video_duration_seconds,
        final_video_width=1080,
        final_video_height=1920,
        final_video_fps=24.0,
        final_video_path_or_uri="file:///tmp/final.mp4",
        final_video_has_video_stream=True,
        final_video_has_audio_stream=final_video_has_audio_stream,
        final_audio_duration_seconds=final_audio_duration_seconds,
        final_video_codec="h264",
        final_audio_codec="aac",
        source_asset_duration_seconds=source_asset_duration_seconds,
        source_path_or_uri="file:///tmp/source.mp4",
        creative_duration_seconds=creative_duration_seconds,
        editing_duration_seconds=editing_duration_seconds,
        cover_timestamp_seconds=cover_timestamp_seconds,
    )


def _failure_codes(trace: dict[str, object]) -> set[str]:
    codes = trace.get("failure_codes")
    assert isinstance(codes, list)
    return {str(code) for code in codes}


def test_12_second_plan_10_second_video_fails_validation() -> None:
    trace = _trace(final_video_duration_seconds=10.0, editing_duration_seconds=10.0)
    assert "creative_duration_mismatch" in _failure_codes(trace)


def test_missing_audio_fails_timeline_validation() -> None:
    trace = _trace(final_video_has_audio_stream=False, final_audio_duration_seconds=None)
    assert "final_video_missing_audio" in _failure_codes(trace)
    assert "audio_video_duration_mismatch" in _failure_codes(trace)


def test_audio_shorter_than_video_fails_or_is_padded_and_logged() -> None:
    trace = _trace(final_audio_duration_seconds=10.0)
    assert "audio_video_duration_mismatch" in _failure_codes(trace)


def test_audio_longer_than_video_fails_or_is_trimmed_and_logged() -> None:
    trace = _trace(final_audio_duration_seconds=13.0)
    assert "audio_video_duration_mismatch" in _failure_codes(trace)


def test_overlay_exceeding_final_duration_fails() -> None:
    timeline = {
        **_TIMELINE,
        "overlays": [
            {
                "overlay_id": "overlay-001",
                "start_seconds": 11.0,
                "end_seconds": 13.0,
                "text": "Too late",
            }
        ],
    }
    trace = _trace(canonical_timeline=timeline)
    assert "overlay_exceeds_video_duration" in _failure_codes(trace)


def test_scene_exceeding_final_duration_fails() -> None:
    timeline = {
        **_TIMELINE,
        "scenes": [{"scene_id": "scene-001", "start_seconds": 0.0, "end_seconds": 13.0}],
    }
    trace = _trace(canonical_timeline=timeline)
    assert "scene_exceeds_video_duration" in _failure_codes(trace)


def test_cover_timestamp_outside_duration_fails() -> None:
    trace = _trace(cover_timestamp_seconds=13.0)
    assert "cover_timestamp_out_of_bounds" in _failure_codes(trace)


def test_timeline_render_trace_written_to_package(tmp_path: Path) -> None:
    final_video = tmp_path / "input-video.mp4"
    cover = tmp_path / "input-cover.png"
    final_video.write_bytes(b"video-bytes")
    cover.write_bytes(b"png-bytes")
    trace = _trace()

    package = build_package_directory(
        reel_id="reel-timeline",
        final_video_path=final_video,
        cover_path=cover,
        caption_variants="Caption",
        posting_plan={},
        provenance={},
        timeline=_TIMELINE,
        timeline_render_trace=trace,
        overlay_render_trace={
            "artifact_type": "overlay_render_trace",
            "schema_version": "rendered_overlay_manifest_v1",
            "overlay_count": 0,
            "overlays": [],
        },
        temp_root=tmp_path / "scratch",
    )

    assert (package.directory / "timeline_render_trace.json").exists()
    assert package.manifest is not None
    artifact_names = {artifact["name"] for artifact in package.manifest["artifacts"]}
    assert "timeline_render_trace" in artifact_names
