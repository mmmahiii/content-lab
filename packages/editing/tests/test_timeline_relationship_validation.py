from __future__ import annotations

from content_lab_editing.timeline_validator import validate_reel_timeline_artifact


def _timeline() -> dict[str, object]:
    return {
        "plan_id": "timeline_relationships",
        "total_duration_seconds": 4.0,
        "fps": 24,
        "canvas": {"aspect_ratio": "9:16", "width": 1080, "height": 1920},
        "objects": [
            {
                "object_id": "surface",
                "asset_id": "surface",
                "scene_id": "scene_1",
                "role": "environment_base",
                "start_time": 0.0,
                "end_time": 4.0,
                "x": 0.5,
                "y": 0.5,
                "z": 0.05,
                "scale": 1.0,
                "width_normalised": 0.9,
                "height_normalised": 0.8,
                "opacity": 1.0,
            },
            {
                "object_id": "hero",
                "asset_id": "hero",
                "scene_id": "scene_1",
                "role": "hero_subject",
                "start_time": 0.0,
                "end_time": 4.0,
                "x": 0.5,
                "y": 0.5,
                "z": 0.7,
                "scale": 1.0,
                "width_normalised": 0.4,
                "height_normalised": 0.3,
                "opacity": 1.0,
                "spatial_relationship": "on_surface",
                "support_object_id": "surface",
                "required_overlap_ratio": 0.1,
                "support_contact_required": True,
                "contact_shadow_target_object_id": "surface",
                "relative_depth_rule": "above_support",
            },
        ],
        "captions": [],
        "camera_moves": [],
        "audio_layers": [],
    }


def test_timeline_relationship_graph_passes() -> None:
    report = validate_reel_timeline_artifact(_timeline())

    assert report.passed is True


def test_timeline_missing_support_id_fails_schema() -> None:
    payload = _timeline()
    payload["objects"][1].pop("support_object_id")  # type: ignore[index,union-attr]

    report = validate_reel_timeline_artifact(payload)

    assert not report.passed
    assert "timeline_schema_invalid" in report.as_dict()["failure_codes"]


def test_timeline_unknown_support_id_fails() -> None:
    payload = _timeline()
    payload["objects"][1]["support_object_id"] = "missing"  # type: ignore[index]

    report = validate_reel_timeline_artifact(payload)

    assert not report.passed
    assert "support_object_not_found" in report.as_dict()["failure_codes"]


def test_timeline_inside_relationship_requires_overlap_and_depth() -> None:
    payload = _timeline()
    hero = payload["objects"][1]  # type: ignore[index]
    hero["spatial_relationship"] = "inside"
    hero["required_overlap_ratio"] = 0.8
    hero["x"] = 0.98

    report = validate_reel_timeline_artifact(payload)

    assert not report.passed
    assert "relationship_required_overlap_not_met" in report.as_dict()["failure_codes"]


def test_timeline_behind_hero_depth_rule_fails() -> None:
    payload = _timeline()
    reveal = dict(payload["objects"][0])  # type: ignore[index]
    reveal.update(
        {
            "object_id": "reveal",
            "asset_id": "reveal",
            "role": "background_reveal",
            "z": 0.9,
            "relative_depth_rule": "behind_hero",
            "x": 0.1,
        }
    )
    payload["objects"].append(reveal)  # type: ignore[union-attr]

    report = validate_reel_timeline_artifact(payload)

    assert not report.passed
    assert "behind_hero_depth_invalid" in report.as_dict()["failure_codes"]
