from __future__ import annotations

from content_lab_core.types import QAVerdict
from content_lab_qa.timing import (
    TimelineTimingConstraints,
    evaluate_timeline_timing_qa,
)


def test_evaluate_timeline_timing_qa_passes_aligned_payload() -> None:
    result = evaluate_timeline_timing_qa(
        script={
            "overlay_timeline": [
                {"start_seconds": 0, "end_seconds": 1, "text": "h", "emphasis": "hook"},
            ],
        },
        scene_plan={"scenes": [{"scene_id": "s", "start_seconds": 0, "end_seconds": 5}]},
        editing={"duration_seconds": 5.0},
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
        editing={"duration_seconds": 10.0},
        constraints=TimelineTimingConstraints(min_final_cta_duration_seconds=1.5),
    )
    assert result.verdict == QAVerdict.FAIL
    report = result.details.get("report")
    assert isinstance(report, dict)
    assert report.get("failed") is True
