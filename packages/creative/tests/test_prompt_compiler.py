from __future__ import annotations

from content_lab_core.types import Platform
from content_lab_creative.director import PhaseOneDirector
from content_lab_creative.persona import PageConstraints, PageMetadata, PersonaProfile
from content_lab_creative.prompt_compiler import CompiledProviderPrompt, compile_provider_prompt
from content_lab_creative.scene_plan import compile_scene_plan
from content_lab_creative.script_generator import generate_script_output
from content_lab_creative.types import (
    DirectorPlanInput,
    PolicyStateDocument,
    SceneOverlayRole,
    ScenePlanOutput,
    ScenePlanScene,
    ScenePurpose,
)
from content_lab_creative.visual_lint import lint_scene_visual_specificity


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


def _compiled_prompt() -> CompiledProviderPrompt:
    brief = PhaseOneDirector().plan(_planned_brief())
    script = generate_script_output(brief)
    scene_plan = compile_scene_plan(brief=brief, script=script)
    return compile_provider_prompt(
        brief_payload=brief.model_dump(mode="json"),
        scene_plan=scene_plan,
        provider="runway",
        model="gen4.5",
    )


def test_prompt_compiler_is_deterministic_for_equivalent_inputs() -> None:
    first = _compiled_prompt()
    second = _compiled_prompt()

    assert first.model_dump() == second.model_dump()
    assert first.trace.prompt_hash == second.trace.prompt_hash


def test_prompt_trace_shape_links_brief_scene_plan_and_final_prompt() -> None:
    compiled = _compiled_prompt()

    assert compiled.prompt_kind == "scene_plan_visual_prompt"
    assert compiled.trace.compiler_name == "scene_prompt_compiler_v2"
    assert compiled.trace.source.brief_title.startswith("Northwind Fitness")
    assert len(compiled.trace.source.scene_ids) == 5
    assert [fragment.scene_id for fragment in compiled.trace.fragments] == (
        compiled.trace.source.scene_ids
    )
    assert compiled.trace.final_prompt_chars == len(compiled.prompt)
    assert compiled.trace.safety.negative_prompt == compiled.negative_prompt


def test_prompt_compiler_removes_meta_language_from_compiled_prompt() -> None:
    scene_plan = ScenePlanOutput(
        brief_title="Mobility reset",
        duration_seconds=10,
        scenes=[
            ScenePlanScene(
                scene_id="scene_1_hook",
                purpose=ScenePurpose.HOOK,
                start_seconds=0,
                end_seconds=5,
                visual_intent="Fresh angle for the page persona with visual intent notes.",
                shot_guidance="Set up the shot guidance in a plain-language step.",
                overlay_role=SceneOverlayRole.HOOK,
            ),
            ScenePlanScene(
                scene_id="scene_2_close",
                purpose=ScenePurpose.CLOSE,
                start_seconds=5,
                end_seconds=10,
                visual_intent="Person finishes one slow shoulder reset beside a desk.",
                shot_guidance="Stable vertical close-up, natural daylight.",
                overlay_role=SceneOverlayRole.CTA,
            ),
        ],
    )

    compiled = compile_provider_prompt(
        brief_payload={"title": "Mobility reset", "content_pillar": "mobility"},
        scene_plan=scene_plan,
        provider="runway",
        model="gen4.5",
    )

    lowered = compiled.prompt.lower()
    assert "fresh angle" not in lowered
    assert "persona" not in lowered
    assert "visual intent" not in lowered
    assert "shot guidance" not in lowered
    assert "plain-language step" not in lowered
    assert "person finishes one slow shoulder reset" in lowered
    assert compiled.trace.safety.removed_meta_language is True


def test_prompt_compiler_preserves_provider_safe_limits_and_negative_prompt() -> None:
    compiled = _compiled_prompt()

    assert len(compiled.prompt) <= compiled.trace.safety.max_prompt_chars
    assert all(
        len(fragment.prompt_text) <= compiled.trace.safety.max_scene_fragment_chars
        for fragment in compiled.trace.fragments
    )
    assert compiled.negative_prompt == "text overlays, captions, watermarks"


def test_prompt_compiler_uses_subject_setting_action_object_camera() -> None:
    brief = PhaseOneDirector().plan(_operations_brief())
    script = generate_script_output(brief)
    scene_plan = compile_scene_plan(brief=brief, script=script)
    compiled = compile_provider_prompt(
        brief_payload=brief.model_dump(mode="json"),
        scene_plan=scene_plan,
        provider="runway",
        model="gen4.5",
    )

    lowered = compiled.prompt.lower()
    assert "busy founder" in lowered
    assert "modern desk workspace" in lowered
    assert "dragging overdue tasks" in lowered
    assert "non-readable interface blocks" in lowered
    assert "close-up over-the-shoulder" in lowered


def test_prompt_compiler_blocks_visual_focus_filler() -> None:
    brief = PhaseOneDirector().plan(_operations_brief())
    script = generate_script_output(brief)
    scene_plan = compile_scene_plan(brief=brief, script=script)
    compiled = compile_provider_prompt(
        brief_payload=brief.model_dump(mode="json"),
        scene_plan=scene_plan,
        provider="runway",
        model="gen4.5",
    )

    assert "visual focus" not in compiled.prompt.lower()
    assert compiled.trace.safety.generic_filler_removed is True


def test_prompt_includes_no_legible_text_instruction_for_screen_ui() -> None:
    brief = PhaseOneDirector().plan(_operations_brief())
    script = generate_script_output(brief)
    scene_plan = compile_scene_plan(brief=brief, script=script)
    compiled = compile_provider_prompt(
        brief_payload=brief.model_dump(mode="json"),
        scene_plan=scene_plan,
        provider="runway",
        model="gen4.5",
    )

    assert "no legible text on screens" in compiled.prompt.lower()
    assert compiled.trace.safety.no_legible_text_instruction_applied is True


def test_visual_prompt_lint_flags_generic_scene_prompt() -> None:
    result = lint_scene_visual_specificity(
        {
            "visual_intent": "visual focus operations",
            "shot_guidance": "show value",
            "subject": "",
            "setting": "desk",
            "action": "",
            "key_visual_object": "",
            "camera_framing": "",
        },
        prompt_text="visual focus operations useful step",
    )

    assert result.passed is False
    assert "generic_phrase:visual focus" in result.findings
    assert "missing_field:action" in result.findings
