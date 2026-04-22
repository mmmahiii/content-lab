from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_lab_core.types import Platform
from content_lab_creative.director import PhaseOneDirector
from content_lab_creative.persona import PageConstraints, PageMetadata, PersonaProfile
from content_lab_creative.scene_plan import compile_scene_plan, compile_scene_prompt
from content_lab_creative.script_generator import generate_script_output
from content_lab_creative.types import (
    DirectorPlanInput,
    PolicyStateDocument,
    SceneOverlayRole,
    ScenePlanOutput,
    ScenePlanScene,
    ScenePurpose,
)


def _planned_brief() -> DirectorPlanInput:
    return DirectorPlanInput(
        page_name="Northwind Fitness",
        brief_index=0,
        target_platforms=[Platform.INSTAGRAM],
        page_metadata=PageMetadata(
            persona=PersonaProfile(
                label="Coach-next-door",
                audience="Busy professionals who want practical routines",
                brand_tone=["direct", "optimistic"],
                content_pillars=["mobility", "strength"],
                differentiators=["simple progressions"],
                primary_call_to_action="Follow for the next routine",
            ),
            constraints=PageConstraints(required_disclosures=["Results vary"]),
        ),
        global_policy=PolicyStateDocument(),
    )


def test_scene_plan_schema_accepts_valid_timeline() -> None:
    plan = ScenePlanOutput(
        brief_title="Mobility reset",
        duration_seconds=10,
        scenes=[
            ScenePlanScene(
                scene_id="scene_1_hook",
                purpose=ScenePurpose.HOOK,
                start_seconds=0,
                end_seconds=5,
                visual_intent="Show the result immediately.",
                shot_guidance="Open tight on the movement.",
                overlay_role=SceneOverlayRole.HOOK,
                overlay_text="Mobility reset",
                narration_refs=[0],
            ),
            ScenePlanScene(
                scene_id="scene_2_close",
                purpose=ScenePurpose.CLOSE,
                start_seconds=5,
                end_seconds=10,
                visual_intent="Resolve with one useful takeaway.",
                shot_guidance="Hold on the final frame.",
                overlay_role=SceneOverlayRole.CTA,
                overlay_text="Save this reset",
                narration_refs=[1],
            ),
        ],
    )

    assert plan.schema_version == "phase_1"
    assert plan.scenes[0].purpose is ScenePurpose.HOOK


def test_scene_plan_schema_rejects_timeline_gaps() -> None:
    with pytest.raises(ValidationError):
        ScenePlanOutput(
            brief_title="Mobility reset",
            duration_seconds=12,
            scenes=[
                ScenePlanScene(
                    scene_id="scene_1_hook",
                    purpose=ScenePurpose.HOOK,
                    start_seconds=0,
                    end_seconds=5,
                    visual_intent="Show the result immediately.",
                    shot_guidance="Open tight on the movement.",
                    overlay_role=SceneOverlayRole.HOOK,
                ),
                ScenePlanScene(
                    scene_id="scene_2_close",
                    purpose=ScenePurpose.CLOSE,
                    start_seconds=7,
                    end_seconds=12,
                    visual_intent="Resolve with one useful takeaway.",
                    shot_guidance="Hold on the final frame.",
                    overlay_role=SceneOverlayRole.CTA,
                ),
            ],
        )


def test_compile_scene_plan_is_deterministic_and_purposeful() -> None:
    brief = PhaseOneDirector().plan(_planned_brief())
    script = generate_script_output(brief)

    first = compile_scene_plan(brief=brief, script=script)
    second = compile_scene_plan(brief=brief, script=script)

    assert first.model_dump() == second.model_dump()
    assert [scene.purpose for scene in first.scenes] == [
        ScenePurpose.HOOK,
        ScenePurpose.SETUP,
        ScenePurpose.VALUE,
        ScenePurpose.PAYOFF,
        ScenePurpose.CLOSE,
    ]
    assert first.scenes[0].start_seconds == 0
    assert first.scenes[-1].end_seconds == script.duration_seconds
    assert all(scene.visual_intent for scene in first.scenes)
    assert all(scene.shot_guidance for scene in first.scenes)


def test_compile_scene_prompt_uses_scene_level_guidance() -> None:
    brief = PhaseOneDirector().plan(_planned_brief())
    script = generate_script_output(brief)
    plan = compile_scene_plan(brief=brief, script=script)

    prompt = compile_scene_prompt(plan)

    assert "hook:" in prompt
    assert "setup:" in prompt
    assert "payoff:" in prompt
    assert "Shot:" in prompt
