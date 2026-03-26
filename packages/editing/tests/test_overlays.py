from __future__ import annotations

from content_lab_editing.instructions import EditInstruction, EditOperation, EditPlan
from content_lab_editing.overlays import (
    TextOverlay,
    build_drawtext_filters,
    build_overlay_video_filter,
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
