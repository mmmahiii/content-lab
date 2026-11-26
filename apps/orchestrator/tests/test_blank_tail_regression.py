"""Regression: idea-plan reels used to show no text for the last ~4 s.

``build_canonical_timeline`` pinned overlay cue *i* to scene *i*. Saved idea plans have three
beats (hook, value, CTA) and the scene plan always has five scenes, so scenes 4-5 had no cue
and the last 40% of every 10 s smoke-test reel was blank. These tests run the real creative
planning step and check the canonical timeline the editor renders from.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
from content_lab_creative import PolicyStateDocument
from content_lab_storage import CanonicalStorageLayout

from content_lab_api.services.process_reel import ProcessReelExecution
from content_lab_core.types import Platform
from content_lab_orchestrator.flows.process_reel import (
    PhaseOnePlanningContext,
    PhaseOneProcessReelExecutor,
)


def _source_plan(beat_seconds: list[int]) -> dict[str, Any]:
    labels = ["Hook", "Proof", "Action"]
    texts = [
        "Open with the exact problem the audience already feels.",
        "Show the useful shift, example, or operating principle.",
        "Close with one concrete next step the viewer can try.",
    ]
    return {
        "hook": "What would make @test worth following this week?",
        "angle": "Turn one practical page insight into a clear update.",
        "title": "test plan",
        "beats": [
            {"text": texts[i], "label": labels[i], "seconds": seconds}
            for i, seconds in enumerate(beat_seconds)
        ],
        "caption_angles": ["Save this.", "A simple approach.", "Try it today."],
    }


class _Loader:
    def __init__(self, context: PhaseOnePlanningContext) -> None:
        self._context = context

    def load(self, execution: ProcessReelExecution) -> PhaseOnePlanningContext:
        _ = execution
        return self._context


def _creative_output(*, beat_seconds: list[int], duration_seconds: int) -> dict[str, Any]:
    context = PhaseOnePlanningContext(
        page_name="test",
        page_metadata={},
        family_name="test plan",
        family_mode="explore",
        variant_label="Smoke test",
        brief_index=0,
        target_platforms=(Platform.INSTAGRAM,),
        timezone="UTC",
        locale="en",
        policy=PolicyStateDocument(),
        duration_seconds=duration_seconds,
        source_plan=_source_plan(beat_seconds),
    )
    executor = PhaseOneProcessReelExecutor(
        planning_context_loader=_Loader(context),
        asset_resolver=cast(Any, None),
        storage_client=cast(Any, None),
        package_layout=CanonicalStorageLayout(bucket="test"),
    )
    execution = ProcessReelExecution(
        reel_id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        page_id=str(uuid.uuid4()),
        reel_family_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        dry_run=False,
    )
    return executor.create_creative_plan(execution)


def _overlay_spans(creative_output: dict[str, Any]) -> list[tuple[float, float]]:
    overlays = creative_output["canonical_timeline"]["overlays"]
    return [(float(item["start_seconds"]), float(item["end_seconds"])) for item in overlays]


@pytest.mark.parametrize(
    ("beat_seconds", "duration_seconds"),
    [
        ([3, 6, 3], 12),  # the smoke-test plan
        ([4, 4, 4], 12),
        ([2, 5, 3], 10),
        ([5, 10, 5], 20),
    ],
)
def test_idea_plan_overlays_cover_the_whole_reel(
    beat_seconds: list[int], duration_seconds: int
) -> None:
    output = _creative_output(beat_seconds=beat_seconds, duration_seconds=duration_seconds)
    timeline_duration = float(output["canonical_timeline"]["duration_seconds"])
    spans = _overlay_spans(output)

    assert spans[0][0] == pytest.approx(0.0)
    assert spans[-1][1] == pytest.approx(timeline_duration)
    for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
        assert start == pytest.approx(end), f"gap or overlap between cues: {spans}"


def test_idea_plan_overlays_follow_spoken_beats_not_scene_index() -> None:
    output = _creative_output(beat_seconds=[3, 6, 3], duration_seconds=12)
    spoken = output["script"]["spoken_script"]
    beat_spans = [(float(b["start_seconds"]), float(b["end_seconds"])) for b in spoken]

    assert _overlay_spans(output) == beat_spans
    assert len(output["canonical_timeline"]["scenes"]) == 5
