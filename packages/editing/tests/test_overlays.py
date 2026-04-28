from __future__ import annotations

from content_lab_editing.instructions import EditInstruction, EditOperation, EditPlan
from content_lab_editing.overlays import (
    TextOverlay,
    build_drawtext_filters,
    build_overlay_render_report,
    build_overlay_video_filter,
    build_rendered_overlay_manifest,
    normalize_overlay_timeline,
)


def test_build_drawtext_filters_uses_safe_defaults_for_edit_plan() -> None:
    timeline = EditPlan(
        run_id="run-overlay",
        instructions=[
            EditInstruction(operation=EditOperation.TRIM, params={"start": 0, "end": 1}),
            EditInstruction(
                operation=EditOperation.OVERLAY_TEXT,
                params={
                    "text": "Hello: world",
                    "start": 0.25,
                    "duration": 0.5,
                },
            ),
        ],
    )

    filters = build_drawtext_filters(timeline, clip_duration_seconds=1.5)

    assert len(filters) == 1
    assert "drawtext=" in filters[0]
    assert "text='Hello\\: world'" in filters[0]
    assert "x=(w-text_w)/2" in filters[0]
    assert "y=h-text_h-160" in filters[0]
    assert "box=1" in filters[0]
    assert "enable='between(t,0.250,0.750)'" in filters[0]


def test_normalize_overlay_timeline_clamps_open_ended_overlay_to_clip_duration() -> None:
    overlays = normalize_overlay_timeline(
        [TextOverlay(text="Later", start_seconds=0.9)],
        clip_duration_seconds=1.2,
    )

    assert overlays[0].start_seconds == 0.9
    assert overlays[0].end_seconds == 1.2


def test_build_overlay_video_filter_leaves_base_filter_untouched_without_overlays() -> None:
    assert (
        build_overlay_video_filter(base_filter="scale=1080:1920", timeline=None)
        == "scale=1080:1920"
    )


def test_build_overlay_render_report_traces_timeline_and_scene_plan_references() -> None:
    timeline = [
        {
            "text": "  Hook line  ",
            "start_seconds": 0,
            "end_seconds": 2,
            "emphasis": "hook",
        },
        {
            "text": "Value line",
            "start_seconds": 2,
            "end_seconds": 4,
            "overlay_role": "value",
        },
    ]
    report = build_overlay_render_report(
        timeline=timeline,
        clip_duration_seconds=5.0,
        scene_plan={
            "scenes": [
                {
                    "scene_id": "s1",
                    "purpose": "hook",
                    "overlay_text": "Scene hook copy",
                    "overlay_role": "hook",
                }
            ]
        },
    )

    assert report["render_authority"] == "overlay_timeline_argument_only"
    assert report["scene_plan_overlay_text_drives_render"] is False
    assert report["ffmpeg_drawtext_truncation"] == "none_pipeline_has_no_text_max_width"

    overlays = report["overlays"]
    assert len(overlays) == 2

    first = overlays[0]
    assert first["source_path"] == "script.overlay_timeline[0]"
    assert first["source_kind"] == "mapping"
    assert first["role"] == "hook"
    assert first["payload_text_raw"] == "  Hook line  "
    assert first["final_render_text"] == "Hook line"
    assert first["truncation_before_render"] == "whitespace_strip"
    assert first["truncation_during_ffmpeg"] == "none"
    assert first["max_width_px"] is None
    assert first["font_size"] == 64
    assert first["start_seconds"] == 0.0
    assert first["end_seconds"] == 2.0
    assert first["x_expression"] == "(w-text_w)/2"
    assert first["y_expression"] == "h-text_h-160"
    assert first["style"]["horizontal_align"] == "center"
    assert "Hook line" in first["drawtext_filter"]

    second = overlays[1]
    assert second["source_path"] == "script.overlay_timeline[1]"
    assert second["role"] == "value"

    refs = report["scene_plan_overlay_text_references"]
    assert len(refs) == 1
    assert refs[0]["overlay_text"] == "Scene hook copy"
    assert refs[0]["used_for_video_render"] is False


def test_build_rendered_overlay_manifest_collision_groups_time_overlap() -> None:
    timeline = [
        {"text": "A", "start_seconds": 0, "end_seconds": 2},
        {"text": "B", "start_seconds": 1, "end_seconds": 3},
        {"text": "C", "start_seconds": 5, "end_seconds": 6},
    ]
    manifest = build_rendered_overlay_manifest(
        timeline=timeline,
        clip_duration_seconds=10.0,
        frame_width_px=1080,
        frame_height_px=1920,
    )

    assert manifest.schema_version == "rendered_overlay_manifest_v1"
    assert len(manifest.overlays) == 3
    assert manifest.overlays[0].collision_group == manifest.overlays[1].collision_group
    assert manifest.overlays[2].collision_group != manifest.overlays[0].collision_group
    assert manifest.overlays[0].wrap_lines == ("A",)
    assert manifest.overlays[0].safe_area["frame_width_px"] == 1080


def test_build_rendered_overlay_manifest_empty_timeline() -> None:
    manifest = build_rendered_overlay_manifest(
        timeline=None,
        clip_duration_seconds=3.0,
        frame_width_px=1080,
        frame_height_px=1920,
    )
    assert manifest.overlays == ()
