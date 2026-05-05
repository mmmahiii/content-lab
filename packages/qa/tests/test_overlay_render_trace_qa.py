from __future__ import annotations

from typing import Any

from content_lab_core.types import QAVerdict
from content_lab_qa.package import validate_package_overlay_render_trace


def _package_with_overlay(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timeline": {"duration_seconds": 6.0},
        "overlay_render_trace": {
            "artifact_type": "overlay_render_trace",
            "schema_version": "rendered_overlay_manifest_v1",
            "frame_width_px": 1080,
            "frame_height_px": 1920,
            "clip_duration_seconds": 6.0,
            "overlays": [row],
        },
    }


def _trace_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "source_text": "The operations reset busy founders can do today",
        "rendered_text": "The operations reset busy founders can do today",
        "start_seconds": 0.0,
        "end_seconds": 3.0,
        "visible_start_seconds": 0.0,
        "visible_end_seconds": 3.0,
        "role": "hook",
        "font_size": 64,
        "line_count": 2,
        "wrap_lines": ["The operations reset busy", "founders can do today"],
        "x_position": "(w-text_w)/2",
        "y_position": "h-text_h-160",
        "box_width_px": 800,
        "box_height_px": 180,
        "clipped": False,
        "safe_area_passed": True,
        "collision_check": "passed",
    }
    row.update(overrides)
    return row


def _codes(payload: dict[str, Any]) -> set[str]:
    result = validate_package_overlay_render_trace(payload)
    assert result.verdict == QAVerdict.FAIL
    findings = result.details["findings"]
    assert isinstance(findings, list)
    return {str(item["code"]) for item in findings}


def test_overlay_text_mismatch_fails_qa() -> None:
    payload = _package_with_overlay(_trace_row(rendered_text="The operations reset busy founders"))
    assert {"overlay_text_mismatch", "hook_incomplete"} <= _codes(payload)


def test_overlay_clipping_fails_qa() -> None:
    payload = _package_with_overlay(_trace_row(clipped=True, safe_area_passed=False))
    assert {"overlay_text_clipped", "overlay_safe_area_failed"} <= _codes(payload)


def test_overlay_collision_fails_qa() -> None:
    first = _trace_row(collision_check="failed")
    second = _trace_row(
        source_text="Second",
        rendered_text="Second",
        start_seconds=2.0,
        end_seconds=4.0,
        visible_start_seconds=2.0,
        visible_end_seconds=4.0,
        role="emphasis",
    )
    payload = _package_with_overlay(first)
    payload["overlay_render_trace"]["overlays"].append(second)
    assert "overlay_collision_detected" in _codes(payload)


def test_overlay_readability_too_fast_fails_qa() -> None:
    payload = _package_with_overlay(_trace_row(visible_end_seconds=0.4))
    assert "overlay_readability_failed" in _codes(payload)
