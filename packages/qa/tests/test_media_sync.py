from __future__ import annotations

from content_lab_core.types import QAVerdict
from content_lab_qa.timing import evaluate_media_sync_qa


def _editing_payload(*, final_duration: float = 5.0) -> dict[str, object]:
    return {
        "duration_seconds": final_duration,
        "cover_frame_timestamp_seconds": 0.0,
        "timeline": {
            "duration_seconds": final_duration,
            "scenes": [{"scene_id": "s1", "start_seconds": 0.0, "end_seconds": final_duration}],
            "overlays": [
                {"overlay_id": "o1", "start_seconds": 0.0, "end_seconds": 1.0, "text": "x"}
            ],
            "audio_tracks": [
                {"track_id": "audio-master", "start_seconds": 0.0, "end_seconds": final_duration}
            ],
        },
        "timeline_render_trace": {
            "audio_timings": [
                {"track_id": "audio-master", "start_seconds": 0.0, "end_seconds": final_duration}
            ],
            "checks": {
                "video_stream": {"passed": True, "code": "final_video_missing_video"},
                "audio_stream": {"passed": True, "code": "final_video_missing_audio"},
                "audio_video_sync": {
                    "passed": True,
                    "code": "audio_video_duration_mismatch",
                },
                "duration_alignment": {"passed": True, "code": "editing_duration_mismatch"},
                "creative_duration": {"passed": True, "code": "creative_duration_mismatch"},
                "scene_bounds": {"passed": True, "code": "scene_exceeds_video_duration"},
                "overlay_bounds": {"passed": True, "code": "overlay_exceeds_video_duration"},
                "cover_timestamp": {"passed": True, "code": "cover_timestamp_out_of_bounds"},
                "source_asset_duration": {"passed": True, "code": "source_asset_too_short"},
            },
            "duration_mismatch_checks": {"status": "pass", "mismatches": []},
        },
    }


def test_media_sync_gate_passes_aligned_payload() -> None:
    result = evaluate_media_sync_qa(editing=_editing_payload(final_duration=5.0))
    assert result.verdict == QAVerdict.PASS


def test_media_sync_gate_allows_probe_float_noise_at_frame_boundary() -> None:
    payload = _editing_payload(final_duration=10.041667)
    timeline = payload["timeline"]
    assert isinstance(timeline, dict)
    timeline["duration_seconds"] = 10.0
    timeline["audio_tracks"] = [
        {"track_id": "audio-master", "start_seconds": 0.0, "end_seconds": 10.0}
    ]
    trace = payload["timeline_render_trace"]
    assert isinstance(trace, dict)
    trace["audio_timings"] = [
        {"track_id": "audio-master", "start_seconds": 0.0, "end_seconds": 10.0}
    ]

    result = evaluate_media_sync_qa(editing=payload)
    assert result.verdict == QAVerdict.PASS


def test_media_sync_gate_fails_all_required_conditions() -> None:
    payload = _editing_payload(final_duration=5.0)
    timeline = payload["timeline"]
    assert isinstance(timeline, dict)
    timeline["duration_seconds"] = 6.5
    timeline["overlays"] = [
        {"overlay_id": "o1", "start_seconds": 0.0, "end_seconds": 7.0, "text": "x"}
    ]
    timeline["scenes"] = [{"scene_id": "s1", "start_seconds": 0.0, "end_seconds": 8.0}]
    timeline["audio_tracks"] = [
        {"track_id": "audio-master", "start_seconds": 0.0, "end_seconds": 6.0}
    ]
    payload["cover_frame_timestamp_seconds"] = 9.0
    trace = payload["timeline_render_trace"]
    assert isinstance(trace, dict)
    trace["duration_mismatch_checks"] = {
        "status": "fail",
        "mismatches": [{"code": "final_vs_scene_plan"}],
    }
    trace["audio_timings"] = [
        {"track_id": "audio-master", "start_seconds": 0.0, "end_seconds": 6.0}
    ]
    trace["checks"] = {
        "audio_stream": {
            "passed": False,
            "code": "final_video_missing_audio",
            "message": "missing audio",
        }
    }

    result = evaluate_media_sync_qa(editing=payload)
    assert result.verdict == QAVerdict.FAIL
    findings = result.details.get("findings")
    assert isinstance(findings, list)
    codes = {str(item.get("code")) for item in findings if isinstance(item, dict)}
    assert "creative_duration_mismatch" in codes
    assert "audio_video_duration_mismatch" in codes
    assert "overlay_exceeds_video_duration" in codes
    assert "cover_timestamp_out_of_bounds" in codes
    assert "scene_exceeds_video_duration" in codes
    assert "final_video_missing_audio" in codes
