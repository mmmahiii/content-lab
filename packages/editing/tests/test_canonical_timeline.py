from __future__ import annotations

import pytest

from content_lab_editing.canonical_timeline import CanonicalTimeline, build_canonical_timeline
from content_lab_editing.media_timeline import build_timeline_render_trace


def test_build_canonical_timeline_derives_overlay_timing_from_scenes() -> None:
    timeline = build_canonical_timeline(
        timeline_id="timeline-1",
        duration_seconds=4.0,
        source_uri="s3://bucket/source.mp4",
        scene_plan={
            "scenes": [
                {"scene_id": "scene-1", "start_seconds": 0.0, "end_seconds": 2.0},
                {"scene_id": "scene-2", "start_seconds": 2.0, "end_seconds": 4.0},
            ]
        },
        overlay_timeline=[
            {"overlay_id": "ov-1", "text": "Hook", "start_seconds": 0.8, "end_seconds": 1.1},
            {"overlay_id": "ov-2", "text": "Value", "scene_id": "scene-2"},
        ],
        spoken_script=None,
    )
    assert timeline.overlays[0].start_seconds == pytest.approx(0.0)
    assert timeline.overlays[0].end_seconds == pytest.approx(2.0)
    assert timeline.overlays[1].start_seconds == pytest.approx(2.0)
    assert timeline.overlays[1].end_seconds == pytest.approx(4.0)


def test_canonical_timeline_rejects_overlapping_overlays_without_explicit_allowance() -> None:
    with pytest.raises(ValueError, match="cannot overlap unless explicitly allowed"):
        CanonicalTimeline.model_validate(
            {
                "timeline_id": "timeline-overlap",
                "duration_seconds": 4.0,
                "cover_frame_timestamp_seconds": 0.0,
                "source_clips": [
                    {
                        "clip_id": "source-001",
                        "duration_seconds": 4.0,
                        "uri": "s3://bucket/source.mp4",
                    }
                ],
                "scenes": [
                    {
                        "scene_id": "scene-1",
                        "start_seconds": 0.0,
                        "end_seconds": 4.0,
                        "source_clip_id": "source-001",
                        "source_start_seconds": 0.0,
                        "source_end_seconds": 4.0,
                    }
                ],
                "edit_segments": [
                    {
                        "segment_id": "segment-1",
                        "timeline_start_seconds": 0.0,
                        "timeline_end_seconds": 4.0,
                        "source_clip_id": "source-001",
                        "source_start_seconds": 0.0,
                        "source_end_seconds": 4.0,
                    }
                ],
                "overlays": [
                    {"overlay_id": "ov-1", "start_seconds": 0.0, "end_seconds": 2.5, "text": "A"},
                    {"overlay_id": "ov-2", "start_seconds": 2.0, "end_seconds": 4.0, "text": "B"},
                ],
                "audio_tracks": [
                    {"track_id": "audio-master", "start_seconds": 0.0, "end_seconds": 4.0}
                ],
            }
        )


def test_canonical_timeline_contains_video_audio_scene_overlay_cover_fields() -> None:
    timeline = build_canonical_timeline(
        timeline_id="timeline-fields",
        duration_seconds=12.0,
        source_uri="s3://bucket/source.mp4",
        scene_plan={
            "scenes": [
                {"scene_id": "scene-1", "start_seconds": 0.0, "end_seconds": 6.0},
                {"scene_id": "scene-2", "start_seconds": 6.0, "end_seconds": 12.0},
            ]
        },
        overlay_timeline=[{"overlay_id": "ov-1", "text": "Hook", "scene_id": "scene-1"}],
        spoken_script=None,
        cover_frame_timestamp_seconds=0.5,
    ).model_dump(mode="json")

    trace = build_timeline_render_trace(
        canonical_timeline=timeline,
        final_video_duration_seconds=12.0,
        final_video_width=1080,
        final_video_height=1920,
        final_video_fps=24.0,
        final_video_path_or_uri="file:///tmp/final_video.mp4",
        final_video_has_video_stream=True,
        final_video_has_audio_stream=True,
        final_audio_duration_seconds=12.0,
        final_video_codec="h264",
        final_audio_codec="aac",
        source_asset_duration_seconds=12.0,
        source_path_or_uri="s3://bucket/source.mp4",
        creative_duration_seconds=12.0,
        editing_duration_seconds=12.0,
        cover_timestamp_seconds=0.5,
    )

    assert trace["schema_version"] == "media_timeline_v1"
    assert trace["creative"]["duration_seconds"] == pytest.approx(12.0)
    assert trace["source_video"]["duration_seconds"] == pytest.approx(12.0)
    assert trace["final_video"]["duration_seconds"] == pytest.approx(12.0)
    assert trace["final_video"]["has_audio_stream"] is True
    assert trace["audio"]["present"] is True
    assert trace["scenes"][0]["scene_id"] == "scene-1"
    assert trace["overlays"][0]["text"] == "Hook"
    assert trace["cover"]["timestamp_seconds"] == pytest.approx(0.5)
    assert trace["checks"]["duration_alignment"]["passed"] is True
    assert trace["checks"]["audio_video_sync"]["passed"] is True
