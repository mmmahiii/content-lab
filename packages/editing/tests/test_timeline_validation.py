from __future__ import annotations

from content_lab_editing.timeline_validation import (
    DEFAULT_FRAME_TOLERANCE_SECONDS,
    validate_timeline_against_final_duration,
)


def test_accepts_overlays_and_scenes_within_final_duration() -> None:
    report = validate_timeline_against_final_duration(
        overlay_timeline=[
            {"start_seconds": 0, "end_seconds": 2, "text": "a", "emphasis": "hook"},
            {
                "start_seconds": 8,
                "end_seconds": 10,
                "text": "cta",
                "emphasis": "cta",
            },
        ],
        scene_plan={
            "scenes": [
                {"scene_id": "a", "start_seconds": 0, "end_seconds": 5},
                {"scene_id": "b", "start_seconds": 5, "end_seconds": 10},
            ]
        },
        final_duration_seconds=10.0,
        frame_tolerance_seconds=DEFAULT_FRAME_TOLERANCE_SECONDS,
        min_final_cta_duration_seconds=0.75,
    )
    assert not report.has_failures


def test_fails_overlay_start_before_zero() -> None:
    report = validate_timeline_against_final_duration(
        overlay_timeline=[
            {"start_seconds": -0.1, "end_seconds": 2, "text": "a", "emphasis": "hook"},
        ],
        scene_plan=None,
        final_duration_seconds=10.0,
    )
    assert report.has_failures
    assert report.findings[0].code == "timeline_overlay_starts_before_zero"


def test_fails_overlay_end_past_final_beyond_tolerance() -> None:
    tol = DEFAULT_FRAME_TOLERANCE_SECONDS
    report = validate_timeline_against_final_duration(
        overlay_timeline=[
            {"start_seconds": 0, "end_seconds": 10.5, "text": "a", "emphasis": "hook"},
        ],
        scene_plan=None,
        final_duration_seconds=10.0,
        frame_tolerance_seconds=tol,
    )
    assert report.has_failures
    codes = {f.code for f in report.findings}
    assert "timeline_overlay_ends_past_final" in codes


def test_allows_end_near_final_within_two_frame_tolerance() -> None:
    tol = DEFAULT_FRAME_TOLERANCE_SECONDS
    report = validate_timeline_against_final_duration(
        overlay_timeline=[
            {"start_seconds": 0, "end_seconds": 10.0 + tol * 0.5, "text": "a", "emphasis": "hook"},
        ],
        scene_plan=None,
        final_duration_seconds=10.0,
        frame_tolerance_seconds=tol,
    )
    assert not report.has_failures


def test_fails_scene_past_final() -> None:
    report = validate_timeline_against_final_duration(
        overlay_timeline=[],
        scene_plan={
            "scenes": [
                {"scene_id": "a", "start_seconds": 0, "end_seconds": 11},
            ]
        },
        final_duration_seconds=10.0,
    )
    assert report.has_failures
    assert any(f.code == "timeline_scene_ends_past_final" for f in report.findings)


def test_fails_final_cta_too_short() -> None:
    report = validate_timeline_against_final_duration(
        overlay_timeline=[
            {
                "start_seconds": 9.5,
                "end_seconds": 9.9,
                "text": "go",
                "emphasis": "cta",
            },
        ],
        scene_plan=None,
        final_duration_seconds=10.0,
        min_final_cta_duration_seconds=1.0,
    )
    assert report.has_failures
    assert any(f.code == "timeline_final_cta_too_short" for f in report.findings)


def test_skips_cta_length_when_no_cta_overlay() -> None:
    report = validate_timeline_against_final_duration(
        overlay_timeline=[
            {"start_seconds": 0, "end_seconds": 2, "text": "h", "emphasis": "hook"},
        ],
        scene_plan=None,
        final_duration_seconds=10.0,
    )
    assert not report.has_failures
    assert not any(f.code == "timeline_final_cta_too_short" for f in report.findings)
