from __future__ import annotations

import pytest

from content_lab_editing.overlay_layout import build_overlay_render_manifest_for_qa
from content_lab_editing.overlays import (
    TextOverlay,
    build_rendered_overlay_manifest,
    normalize_overlay_timeline,
)

LONG_HOOK = "The operations reset busy founders can do today"


def test_overlay_text_fidelity_source_equals_rendered() -> None:
    manifest = build_rendered_overlay_manifest(
        timeline=[
            {
                "text": LONG_HOOK,
                "start_seconds": 0.0,
                "end_seconds": 3.0,
                "emphasis": "hook",
            }
        ],
        clip_duration_seconds=12.0,
        frame_width_px=1080,
        frame_height_px=1920,
    )
    row = manifest.as_json_dict()["overlays"][0]
    assert row["source_text"] == LONG_HOOK
    assert row["rendered_text"] == LONG_HOOK
    assert row["final_render_text"] == LONG_HOOK
    assert row["drawtext_text"] != LONG_HOOK
    assert "can do today" in row["drawtext_text"]


def test_overlay_start_duration_mapping_supported() -> None:
    overlays = normalize_overlay_timeline(
        [{"text": "Start duration", "start": 1.0, "duration": 2.5}],
        clip_duration_seconds=6.0,
    )
    assert overlays[0].start_seconds == pytest.approx(1.0)
    assert overlays[0].end_seconds == pytest.approx(3.5)


def test_overlay_start_seconds_duration_seconds_supported() -> None:
    overlays = normalize_overlay_timeline(
        [{"text": "Start duration", "start_seconds": 1.0, "duration_seconds": 2.5}],
        clip_duration_seconds=6.0,
    )
    assert overlays[0].start_seconds == pytest.approx(1.0)
    assert overlays[0].end_seconds == pytest.approx(3.5)


def test_adjacent_overlay_transitions_do_not_overlap() -> None:
    overlays = normalize_overlay_timeline(
        [
            TextOverlay(text="First", start_seconds=0.0, end_seconds=3.0),
            TextOverlay(text="Second", start_seconds=3.0, end_seconds=6.0),
        ],
        clip_duration_seconds=6.0,
    )
    manifest = build_rendered_overlay_manifest(
        timeline=overlays,
        clip_duration_seconds=6.0,
        frame_width_px=1080,
        frame_height_px=1920,
    )
    rows = manifest.as_json_dict()["overlays"]
    assert rows[0]["visible_end_seconds"] == rows[1]["visible_start_seconds"]
    assert rows[0]["collision_check"] == "passed"
    assert rows[1]["collision_check"] == "passed"


def test_overlay_render_trace_contains_layout_and_collision_fields() -> None:
    manifest = build_rendered_overlay_manifest(
        timeline=[
            {
                "text": LONG_HOOK,
                "start_seconds": 0.0,
                "end_seconds": 3.0,
                "emphasis": "hook",
            }
        ],
        clip_duration_seconds=12.0,
        frame_width_px=1080,
        frame_height_px=1920,
    )
    row = manifest.as_json_dict()["overlays"][0]
    for key in (
        "source_text",
        "rendered_text",
        "start_seconds",
        "end_seconds",
        "visible_start_seconds",
        "visible_end_seconds",
        "role",
        "font_size",
        "line_count",
        "wrap_lines",
        "x_position",
        "y_position",
        "box_width_px",
        "box_height_px",
        "clipped",
        "safe_area_passed",
        "collision_check",
    ):
        assert key in row


def test_regression_operations_reset_hook_trace_preserves_full_text() -> None:
    overlays = normalize_overlay_timeline(
        [
            {
                "text": LONG_HOOK,
                "start_seconds": 0.0,
                "end_seconds": 3.0,
                "emphasis": "hook",
            }
        ],
        clip_duration_seconds=12.0,
    )
    rows, _safe = build_overlay_render_manifest_for_qa(
        overlays,
        frame_width=1080,
        frame_height=1920,
    )
    row = rows[0]
    assert row["source_text"] == LONG_HOOK
    assert row["rendered_text"] == LONG_HOOK
    assert row["layout"]["clipped"] is False
    assert row["layout"]["fits_safe_area"] is True
    assert "\n" in row["drawtext_text"]
    assert "can do today" in row["drawtext_text"]
