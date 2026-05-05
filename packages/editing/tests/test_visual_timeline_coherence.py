from __future__ import annotations

from content_lab_editing.canonical_timeline import (
    build_canonical_timeline,
    infer_edit_mode,
    resolve_stable_cover_timestamp,
)
from content_lab_editing.editor_basic import _overlay_trace_payload
from content_lab_editing.types import RenderedOverlayManifest


def test_scene_timing_aligns_with_canonical_timeline() -> None:
    scene_plan = {
        "scenes": [
            {"scene_id": "hook", "purpose": "hook", "start_seconds": 0, "end_seconds": 3},
            {"scene_id": "value", "purpose": "value", "start_seconds": 3, "end_seconds": 6},
        ]
    }
    timeline = build_canonical_timeline(
        timeline_id="timeline-1",
        duration_seconds=6,
        source_uri="file:///source.mp4",
        scene_plan=scene_plan,
        overlay_timeline=[{"text": "Hook"}, {"text": "Value"}],
        spoken_script=[],
    )

    assert [(scene.start_seconds, scene.end_seconds) for scene in timeline.scenes] == [
        (0.0, 3.0),
        (3.0, 6.0),
    ]
    assert [(overlay.start_seconds, overlay.end_seconds) for overlay in timeline.overlays] == [
        (0.0, 3.0),
        (3.0, 6.0),
    ]


def test_edit_trace_records_single_clip_or_scene_composed_mode() -> None:
    manifest = RenderedOverlayManifest(
        schema_version="rendered_overlay_manifest_v1",
        clip_duration_seconds=6,
        frame_width_px=1080,
        frame_height_px=1920,
        overlays=(),
    )

    assert _overlay_trace_payload(manifest, edit_mode="single_clip")["edit_mode"] == "single_clip"
    assert infer_edit_mode({"scenes": [{"scene_id": "only"}]}) == "single_clip"
    assert infer_edit_mode({"scenes": [{"scene_id": "one"}, {"scene_id": "two"}]}) == (
        "scene_composed"
    )


def test_cover_timestamp_uses_valid_stable_frame_window() -> None:
    timestamp = resolve_stable_cover_timestamp(
        duration_seconds=6.0,
        scenes=[
            {"scene_id": "hook", "start_seconds": 0.0, "end_seconds": 0.4},
            {"scene_id": "value", "start_seconds": 0.4, "end_seconds": 6.0},
        ],
        preferred_timestamp_seconds=0.5,
    )

    assert 0.4 < timestamp < 6.0
