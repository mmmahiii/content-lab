from __future__ import annotations

from content_lab_editing.timeline_validator import validate_reel_timeline_artifact


def _timeline_payload() -> dict[str, object]:
    return {
        "plan_id": "plan_1",
        "total_duration_seconds": 6.5,
        "fps": 24,
        "canvas": {"aspect_ratio": "9:16", "width": 1080, "height": 1920},
        "objects": [
            {
                "object_id": "hero_1",
                "asset_id": "steak_clip",
                "scene_id": "scene_1",
                "start_time": 0.0,
                "end_time": 6.5,
                "x": 0.5,
                "y": 0.52,
                "z": 0.72,
                "scale": 1.0,
                "width_normalised": 0.6,
                "height_normalised": 0.42,
                "opacity": 1.0,
            }
        ],
        "captions": [{"caption_id": "cap_1", "safe_area_compliant": True}],
        "camera_moves": [],
        "audio_layers": [],
    }


def test_reel_timeline_validator_accepts_renderer_ready_coordinates() -> None:
    report = validate_reel_timeline_artifact(_timeline_payload())

    assert report.passed is True
    assert report.findings == ()


def test_reel_timeline_validator_rejects_out_of_frame_objects_and_caption_flags() -> None:
    payload = _timeline_payload()
    payload["objects"][0]["x"] = 0.95  # type: ignore[index]
    payload["captions"][0]["safe_area_compliant"] = False  # type: ignore[index]

    report = validate_reel_timeline_artifact(payload)

    assert not report.passed
    assert "object_likely_out_of_frame" in report.as_dict()["failure_codes"]
    assert "caption_safe_area_violation" in report.as_dict()["failure_codes"]
