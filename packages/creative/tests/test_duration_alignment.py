from __future__ import annotations

import pytest

from content_lab_creative.duration_alignment import (
    assert_rendered_media_matches_plan_duration,
    validate_phase1_creative_duration_alignment,
)


def _minimal_aligned_creative(*, duration: int = 10, include_primary: bool = True) -> dict:
    brief = {"duration_seconds": duration, "title": "t", "other": "x"}
    script = {
        "duration_seconds": duration,
        "overlay_timeline": [
            {"start_seconds": 0, "end_seconds": min(3, duration), "text": "Hi", "emphasis": "hook"},
        ],
    }
    scene_plan = {
        "duration_seconds": duration,
        "scenes": [
            {
                "scene_id": "s1",
                "purpose": "hook",
                "start_seconds": 0,
                "end_seconds": duration,
                "visual_intent": "v",
                "shot_guidance": "s",
                "overlay_role": "hook",
            },
        ],
    }
    posting_plan = {
        "variant": {"variant_label": "A", "duration_seconds": duration},
    }
    out: dict = {
        "brief": brief,
        "script": script,
        "scene_plan": scene_plan,
        "posting_plan": posting_plan,
    }
    if include_primary:
        out["primary_asset_request"] = {"duration_seconds": float(duration)}
    return out


def test_validate_phase1_creative_duration_alignment_accepts_matching_payload() -> None:
    payload = _minimal_aligned_creative(duration=10)
    assert validate_phase1_creative_duration_alignment(payload) == 10


def test_validate_phase1_creative_duration_alignment_rejects_mismatched_primary_request() -> None:
    payload = _minimal_aligned_creative(duration=10)
    payload["primary_asset_request"]["duration_seconds"] = 12
    with pytest.raises(ValueError, match="duration mismatch"):
        validate_phase1_creative_duration_alignment(payload)


def test_validate_phase1_creative_duration_alignment_rejects_overlay_past_timeline() -> None:
    payload = _minimal_aligned_creative(duration=10)
    payload["script"]["overlay_timeline"].append(
        {"start_seconds": 9, "end_seconds": 12, "text": "late", "emphasis": "cta"}
    )
    with pytest.raises(ValueError, match="overlay_timeline"):
        validate_phase1_creative_duration_alignment(payload)


def test_validate_phase1_creative_duration_alignment_rejects_bad_final_scene() -> None:
    payload = _minimal_aligned_creative(duration=10)
    payload["scene_plan"]["scenes"][0]["end_seconds"] = 8
    with pytest.raises(ValueError, match="final scene"):
        validate_phase1_creative_duration_alignment(payload)


def test_validate_phase1_without_primary_asset_request() -> None:
    payload = _minimal_aligned_creative(include_primary=False)
    assert validate_phase1_creative_duration_alignment(
        payload,
        require_primary_asset_request=False,
    ) == 10


def test_assert_rendered_media_matches_plan_duration() -> None:
    assert_rendered_media_matches_plan_duration(
        expected_duration_seconds=10,
        rendered_duration_seconds=9.92,
    )
    with pytest.raises(ValueError, match="Rendered media duration"):
        assert_rendered_media_matches_plan_duration(
            expected_duration_seconds=10,
            rendered_duration_seconds=8.0,
        )


def test_validate_allows_float_primary_duration() -> None:
    payload = _minimal_aligned_creative(duration=10)
    payload["primary_asset_request"]["duration_seconds"] = 10.0
    assert validate_phase1_creative_duration_alignment(payload) == 10
