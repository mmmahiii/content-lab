from __future__ import annotations

import pytest

from content_lab_editing.instructions import EditInstruction, EditOperation, EditPlan
from content_lab_editing.overlays import (
    OverlayTransitionSettings,
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
    assert "enable='gte(t,0.250)*lt(t,0.750)'" in filters[0]


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


def test_adjacent_overlay_handoff_is_half_open_in_enable_expression() -> None:
    overlays = normalize_overlay_timeline(
        [
            TextOverlay(text="A", start_seconds=0.0, end_seconds=3.0),
            TextOverlay(text="B", start_seconds=3.0, end_seconds=6.0),
        ],
        clip_duration_seconds=10.0,
    )
    assert len(overlays) == 2
    filters = build_drawtext_filters(overlays)
    assert "gte(t,0.000)*lt(t,3.000)'" in filters[0]
    assert "gte(t,3.000)*lt(t,6.000)'" in filters[1]


def test_overlapping_overlays_trim_earlier_end_by_default() -> None:
    overlays = normalize_overlay_timeline(
        [
            TextOverlay(text="A", start_seconds=0.0, end_seconds=5.0),
            TextOverlay(text="B", start_seconds=3.0, end_seconds=8.0),
        ],
    )
    assert overlays[0].end_seconds == 3.0
    assert overlays[1].start_seconds == 3.0


def test_allow_overlay_stack_preserves_authored_overlap() -> None:
    overlays = normalize_overlay_timeline(
        [
            TextOverlay(text="A", start_seconds=0.0, end_seconds=5.0),
            TextOverlay(text="B", start_seconds=3.0, end_seconds=8.0),
        ],
        allow_overlay_stack=True,
    )
    assert overlays[0].end_seconds == 5.0
    assert overlays[1].start_seconds == 3.0


def test_handoff_gap_shortens_prior_overlay_before_next_start() -> None:
    overlays = normalize_overlay_timeline(
        [
            TextOverlay(text="A", start_seconds=0.0, end_seconds=3.0),
            TextOverlay(text="B", start_seconds=3.0, end_seconds=6.0),
        ],
        handoff_gap_seconds=0.05,
    )
    assert overlays[0].end_seconds == pytest.approx(2.95)
    assert overlays[1].start_seconds == 3.0


def test_transition_settings_merge_fades_into_drawtext_alpha() -> None:
    transition = OverlayTransitionSettings(enter_duration_ms=200.0, exit_duration_ms=150.0)
    filters = build_drawtext_filters(
        [TextOverlay(text="Hi", start_seconds=0.0, end_seconds=2.0)],
        clip_duration_seconds=5.0,
        transition=transition,
    )
    assert len(filters) == 1
    assert "alpha='" in filters[0]
    assert "max(0.200" in filters[0]
    assert "max(0.150" in filters[0]


def test_fade_timeline_trims_overlap_before_fade_merge() -> None:
    transition = OverlayTransitionSettings(enter_duration_ms=400.0, exit_duration_ms=400.0)
    overlays = normalize_overlay_timeline(
        [
            TextOverlay(text="A", start_seconds=0.0, end_seconds=5.0),
            TextOverlay(text="B", start_seconds=4.0, end_seconds=8.0),
        ],
        transition=transition,
    )
    assert overlays[0].end_seconds == 4.0
    assert overlays[1].start_seconds == 4.0
    assert overlays[0].exit_duration_ms is not None
    assert overlays[0].exit_duration_ms > 0


def test_allow_crossfade_overlap_skips_geometry_trim() -> None:
    transition = OverlayTransitionSettings(allow_crossfade_overlap=True)
    overlays = normalize_overlay_timeline(
        [
            TextOverlay(text="A", start_seconds=0.0, end_seconds=5.0),
            TextOverlay(text="B", start_seconds=3.0, end_seconds=8.0),
        ],
        transition=transition,
    )
    assert overlays[0].end_seconds == 5.0
    assert overlays[1].start_seconds == 3.0


def test_handoff_gap_ms_adds_to_effective_trim_gap() -> None:
    transition = OverlayTransitionSettings(handoff_gap_ms=50.0)
    overlays = normalize_overlay_timeline(
        [
            TextOverlay(text="A", start_seconds=0.0, end_seconds=3.0),
            TextOverlay(text="B", start_seconds=3.0, end_seconds=6.0),
        ],
        transition=transition,
    )
    assert overlays[0].end_seconds == pytest.approx(2.95)
    assert overlays[1].start_seconds == 3.0
