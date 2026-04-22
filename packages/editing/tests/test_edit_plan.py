from __future__ import annotations

import pytest

from content_lab_editing.edit_plan import (
    SceneAwareEditPlan,
    SceneEditPlanSegment,
    build_scene_aware_edit_plan,
    build_single_clip_edit_plan,
)


def test_scene_edit_plan_segment_computes_timeline_end() -> None:
    segment = SceneEditPlanSegment(
        segment_id="segment-001",
        scene_id="scene-hook",
        purpose="hook",
        source_uri="s3://content-lab/assets/hook.mp4",
        duration_seconds=1.5,
        timeline_start_seconds=0.5,
    )

    assert segment.timeline_end_seconds == 2.0


def test_scene_aware_edit_plan_requires_contiguous_segments() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        SceneAwareEditPlan(
            segments=[
                SceneEditPlanSegment(
                    segment_id="segment-001",
                    scene_id="scene-hook",
                    purpose="hook",
                    source_uri="file:///hook.mp4",
                    duration_seconds=1.0,
                    timeline_start_seconds=0.0,
                ),
                SceneEditPlanSegment(
                    segment_id="segment-002",
                    scene_id="scene-value",
                    purpose="value",
                    source_uri="file:///value.mp4",
                    duration_seconds=1.0,
                    timeline_start_seconds=1.5,
                ),
            ]
        )


def test_build_scene_aware_edit_plan_orders_scenes_by_timeline_then_purpose() -> None:
    scene_plan = {
        "schema_version": "phase_1",
        "scenes": [
            {
                "scene_id": "scene-value",
                "purpose": "value",
                "start_seconds": 1,
                "end_seconds": 3,
            },
            {
                "scene_id": "scene-hook",
                "purpose": "hook",
                "start_seconds": 0,
                "end_seconds": 1,
            },
        ],
    }

    plan = build_scene_aware_edit_plan(
        scene_plan=scene_plan,
        scene_asset_uris={
            "scene-hook": "file:///hook.mp4",
            "scene-value": "file:///value.mp4",
        },
    )
    payload = plan.model_dump(mode="json")

    assert [segment["scene_id"] for segment in payload["segments"]] == [
        "scene-hook",
        "scene-value",
    ]
    assert [segment["timeline_start_seconds"] for segment in payload["segments"]] == [0.0, 1.0]
    assert [segment["timeline_end_seconds"] for segment in payload["segments"]] == [1.0, 3.0]
    assert plan.duration_seconds == 3.0
    assert plan.model_dump(mode="json") == build_scene_aware_edit_plan(
        scene_plan=scene_plan,
        scene_asset_uris={
            "scene-hook": "file:///hook.mp4",
            "scene-value": "file:///value.mp4",
        },
    ).model_dump(mode="json")


def test_build_single_clip_edit_plan_keeps_fallback_inspectable() -> None:
    plan = build_single_clip_edit_plan(
        source_uri="file:///single.mp4",
        duration_seconds=1.2,
    )

    assert len(plan.segments) == 1
    assert plan.segments[0].purpose == "single_clip"
    assert plan.metadata["fallback"] == "single_clip"
