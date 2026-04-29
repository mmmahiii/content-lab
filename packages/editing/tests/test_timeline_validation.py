from __future__ import annotations

import pytest

from content_lab_editing.instructions import EditInstruction, EditOperation, EditPlan
from content_lab_editing.overlays import TextOverlay
from content_lab_editing.templates import CALM_EXPLAINER_V1, overlay_transition_settings
from content_lab_editing.timeline_validation import (
    OverlayTimelineCollisionError,
    detect_overlay_collisions,
    validate_overlay_timeline_before_render,
)


def test_detect_collisions_empty_for_adjacent_half_open_boundaries() -> None:
    hits = detect_overlay_collisions(
        [
            TextOverlay(text="A", start_seconds=0.0, end_seconds=3.0),
            TextOverlay(text="B", start_seconds=3.0, end_seconds=6.0),
        ],
        clip_duration_seconds=10.0,
    )
    assert hits == ()


def test_detect_collisions_finds_overlap_with_overlay_ids() -> None:
    timeline = EditPlan(
        run_id="r1",
        instructions=[
            EditInstruction(
                operation=EditOperation.OVERLAY_TEXT,
                params={
                    "text": "First",
                    "overlay_id": "cue-a",
                    "start": 0.0,
                    "end": 5.0,
                },
            ),
            EditInstruction(
                operation=EditOperation.OVERLAY_TEXT,
                params={
                    "text": "Second",
                    "id": "cue-b",
                    "start": 3.0,
                    "end": 8.0,
                },
            ),
        ],
    )
    hits = detect_overlay_collisions(timeline, clip_duration_seconds=10.0)
    assert len(hits) == 1
    assert hits[0].overlay_id_a == "cue-a"
    assert hits[0].overlay_id_b == "cue-b"
    assert hits[0].overlap_start_seconds == pytest.approx(3.0)
    assert hits[0].overlap_end_seconds == pytest.approx(5.0)
    assert "enter_a=" in hits[0].reason


def test_crossfade_template_skips_collision_detection() -> None:
    transition = overlay_transition_settings(CALM_EXPLAINER_V1)
    assert transition.allow_crossfade_overlap is True
    hits = detect_overlay_collisions(
        [
            TextOverlay(text="A", start_seconds=0.0, end_seconds=5.0),
            TextOverlay(text="B", start_seconds=3.0, end_seconds=8.0),
        ],
        clip_duration_seconds=10.0,
        transition=transition,
    )
    assert hits == ()


def test_validate_overlay_timeline_before_render_raises() -> None:
    with pytest.raises(OverlayTimelineCollisionError) as excinfo:
        validate_overlay_timeline_before_render(
            [
                TextOverlay(text="A", start_seconds=0.0, end_seconds=5.0),
                TextOverlay(text="B", start_seconds=3.0, end_seconds=8.0),
            ],
            clip_duration_seconds=10.0,
        )
    err = excinfo.value
    assert len(err.collisions) == 1
    assert err.collisions[0].overlay_id_a == "overlay[0]"
    assert err.collisions[0].overlay_id_b == "overlay[1]"
    assert "overlapping primary" in str(err).lower()
