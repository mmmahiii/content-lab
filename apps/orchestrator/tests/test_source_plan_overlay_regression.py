"""Regression checks for saved idea-plan overlays.

The editing package already guards against FFmpeg/drawtext truncation. These tests
protect the orchestration path that turns saved source plans into overlay cues,
so it cannot silently clip complete sentences before the renderer sees them.
"""

from __future__ import annotations

from typing import Any

from content_lab_creative import PolicyStateDocument
from content_lab_editing.overlays import build_overlay_render_diagnostics

from content_lab_core.types import Platform
from content_lab_orchestrator.flows.process_reel import (
    PhaseOnePlanningContext,
    _script_from_source_plan,
)


def test_source_plan_overlays_do_not_reintroduce_word_clipping() -> None:
    source_plan: dict[str, Any] = {
        "hook": "What would make @test1 worth following this week?",
        "angle": "Turn one practical page insight into a clear short-form reel.",
        "beats": [
            {
                "text": "Open with the exact problem the audience already feels.",
                "label": "Hook",
                "seconds": 3,
            },
            {
                "text": "Show the useful shift, example, or operating principle.",
                "label": "Proof",
                "seconds": 6,
            },
            {
                "text": "Close with one concrete next step the viewer can try.",
                "label": "Action",
                "seconds": 3,
            },
        ],
        "title": "test1 plan 2",
        "caption_angles": [
            "Save this before your next content planning block.",
            "A simple way to turn page strategy into a reel.",
            "Use this as the spine for the next post.",
        ],
    }
    context = PhaseOnePlanningContext(
        page_name="test1",
        page_metadata={},
        family_name="test1 plan 2",
        family_mode="explore",
        variant_label="Smoke test",
        brief_index=2,
        target_platforms=(Platform.INSTAGRAM,),
        timezone="UTC",
        locale="en",
        policy=PolicyStateDocument(),
        duration_seconds=10,
        source_plan=source_plan,
    )

    script = _script_from_source_plan(
        source_plan=source_plan,
        brief_payload={
            "duration_seconds": 10,
            "title": "test1 plan 2",
            "narrative_goal": source_plan["angle"],
        },
        context=context,
    )

    overlay_timeline = [cue.model_dump(mode="json") for cue in script.overlay_timeline]
    overlay_texts = [str(overlay["text"]) for overlay in overlay_timeline]

    assert overlay_texts == [
        "What would make @test1 worth following this week?",
        "Useful shift",
        "One concrete next step",
    ]
    assert "Turn one practical" not in overlay_texts
    assert "Use this as the spine" not in overlay_texts

    diagnostics = build_overlay_render_diagnostics(
        overlay_timeline,
        clip_duration_seconds=10,
    )
    assert [diagnostic.truncation_before_render for diagnostic in diagnostics] == [
        "none",
        "none",
        "none",
    ]
    assert [diagnostic.truncation_during_ffmpeg for diagnostic in diagnostics] == [
        "none",
        "none",
        "none",
    ]
