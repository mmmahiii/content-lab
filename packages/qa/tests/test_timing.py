from __future__ import annotations

from content_lab_core.types import QAVerdict
from content_lab_qa.timing import (
    TimelineTimingConstraints,
    evaluate_timeline_timing_qa,
)


def _timeline(duration_seconds: float = 5.0) -> dict[str, object]:
    return {
        "version": "med-001.v1",
        "timeline_id": "timeline-test",
        "duration_seconds": duration_seconds,
        "cover_frame_timestamp_seconds": 0.0,
        "source_clips": [{"clip_id": "source-001", "duration_seconds": duration_seconds}],
        "scenes": [{"scene_id": "s", "start_seconds": 0.0, "end_seconds": duration_seconds}],
        "edit_segments": [
            {
                "segment_id": "segment-001",
                "timeline_start_seconds": 0.0,
                "timeline_end_seconds": duration_seconds,
                "source_clip_id": "source-001",
                "source_start_seconds": 0.0,
                "source_end_seconds": duration_seconds,
            }
        ],
        "overlays": [],
        "audio_tracks": [
            {
                "track_id": "audio-master",
                "role": "master",
                "start_seconds": 0.0,
                "end_seconds": duration_seconds,
            }
        ],
    }


def test_evaluate_timeline_timing_qa_passes_aligned_payload() -> None:
    result = evaluate_timeline_timing_qa(
        script={
            "overlay_timeline": [
                {"start_seconds": 0, "end_seconds": 1, "text": "h", "emphasis": "hook"},
            ],
        },
        scene_plan={"scenes": [{"scene_id": "s", "start_seconds": 0, "end_seconds": 5}]},
        editing={
            "duration_seconds": 5.0,
            "timeline": _timeline(5.0),
            "cover_frame_timestamp_seconds": 0.0,
        },
    )
    assert result.verdict == QAVerdict.PASS


def test_evaluate_timeline_timing_qa_allows_probe_float_noise_at_frame_boundary() -> None:
    result = evaluate_timeline_timing_qa(
        script={"overlay_timeline": []},
        scene_plan={"scenes": [{"scene_id": "s", "start_seconds": 0, "end_seconds": 10}]},
        editing={
            "duration_seconds": 10.041667,
            "timeline": _timeline(10.0),
            "cover_frame_timestamp_seconds": 0.0,
        },
    )
    assert result.verdict == QAVerdict.PASS


def test_evaluate_timeline_timing_qa_fails_missing_duration() -> None:
    result = evaluate_timeline_timing_qa(
        script={"overlay_timeline": []},
        scene_plan=None,
        editing={},
    )
    assert result.verdict == QAVerdict.FAIL


def test_evaluate_timeline_timing_qa_respects_custom_cta_floor() -> None:
    result = evaluate_timeline_timing_qa(
        script={
            "overlay_timeline": [
                {
                    "start_seconds": 0,
                    "end_seconds": 0.2,
                    "text": "x",
                    "emphasis": "cta",
                },
            ],
        },
        scene_plan=None,
        editing={
            "duration_seconds": 10.0,
            "timeline": {
                **_timeline(10.0),
                "overlays": [
                    {
                        "overlay_id": "ov1",
                        "start_seconds": 0.0,
                        "end_seconds": 0.2,
                        "text": "x",
                        "role": "cta",
                    }
                ],
            },
            "cover_frame_timestamp_seconds": 0.0,
        },
        constraints=TimelineTimingConstraints(min_final_cta_duration_seconds=1.5),
    )
    assert result.verdict == QAVerdict.FAIL
    report = result.details.get("report")
    assert isinstance(report, dict)
    assert report.get("failed") is True
