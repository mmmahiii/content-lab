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


def _operations_brief() -> DirectorPlanInput:
    request = _planned_brief()
    data = request.model_dump()
    data["page_metadata"]["persona"]["content_pillars"] = ["operations"]
    return DirectorPlanInput.model_validate(data)


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


def test_operations_scene_plan_expands_to_concrete_visual_fields() -> None:
    brief = PhaseOneDirector().plan(_operations_brief())
    script = generate_script_output(brief)
    plan = compile_scene_plan(brief=brief, script=script)

    value_scene = next(scene for scene in plan.scenes if scene.purpose is ScenePurpose.VALUE)

    assert value_scene.subject == "busy founder"
    assert value_scene.setting == "modern desk workspace"
    assert "dragging overdue tasks" in str(value_scene.action)
    assert "non-readable interface blocks" in str(value_scene.key_visual_object)
    assert value_scene.camera_framing == "close-up over-the-shoulder"
    assert "legible UI text" in value_scene.forbidden_visual_elements


def test_visual_style_lock_applied_to_all_scenes() -> None:
    brief = PhaseOneDirector().plan(_operations_brief())
    script = generate_script_output(brief)
    plan = compile_scene_plan(brief=brief, script=script)

    assert plan.visual_style_lock["subject"] == "busy founder"
    assert plan.metadata["visual_style_lock"] == plan.visual_style_lock
    assert all(scene.lighting == plan.visual_style_lock["lighting"] for scene in plan.scenes)
    assert all(
        scene.continuity_anchor == plan.visual_style_lock["continuity"] for scene in plan.scenes
    )
