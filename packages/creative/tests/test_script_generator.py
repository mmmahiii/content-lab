from __future__ import annotations

from content_lab_core.types import Platform
from content_lab_creative.brief import CreativeBrief
from content_lab_creative.director import PhaseOneDirector
from content_lab_creative.persona import PageConstraints, PageMetadata, PersonaProfile
from content_lab_creative.script_generator import (
    DeterministicScriptGenerator,
    RulesPlusProviderScriptGenerator,
    build_script_generator,
    generate_script_output,
)
from content_lab_creative.types import (
    DirectorPlanInput,
    GeneratedScriptOutput,
    PolicyStateDocument,
    ScriptGeneratorPath,
    ScriptOverlayEmphasis,
)


def _planned_brief(
    *,
    allow_direct_cta: bool = True,
    max_hashtags: int | None = 4,
) -> DirectorPlanInput:
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
                differentiators=["Simple progressions"],
                primary_call_to_action="Follow for the next routine",
            ),
            constraints=PageConstraints(
                required_disclosures=["Results vary"],
                allow_direct_cta=allow_direct_cta,
                max_hashtags=max_hashtags,
            ),
        ),
        global_policy=PolicyStateDocument(),
    )


def test_deterministic_script_generator_is_stable_for_planned_briefs() -> None:
    brief = PhaseOneDirector().plan(_planned_brief())
    generator = DeterministicScriptGenerator()

    first = generator.generate(brief)
    second = generator.generate(brief)

    assert first.model_dump() == second.model_dump()
    assert first.provider_name == "deterministic_stub"
    assert first.generator_path == "deterministic_stub"
    assert first.generation_metadata["fallback"] is True
    assert first.hook_text == "Mobility reset for busy professionals who want"
    assert [variant.variant.value for variant in first.caption_variants] == [
        "short",
        "standard",
        "engagement",
    ]


def test_deterministic_script_generator_respects_constraints() -> None:
    brief = PhaseOneDirector().plan(_planned_brief(allow_direct_cta=False, max_hashtags=2))

    output = generate_script_output(brief, generator_path=ScriptGeneratorPath.DETERMINISTIC_STUB)

    assert len(output.hashtags) == 2
    assert output.overlay_timeline[-1].emphasis is ScriptOverlayEmphasis.DISCLOSURE
    assert output.overlay_timeline[-1].text == "Results vary"
    assert [comment.purpose.value for comment in output.pinned_comments] == ["disclosure"]


def test_generate_script_output_supports_legacy_creative_brief() -> None:
    brief = CreativeBrief(
        title="Summer Sale Reel",
        description="A short seasonal promo reel.",
        duration_seconds=20,
        tags=["sale", "summer"],
    )

    output = generate_script_output(brief, generator_path="deterministic_stub")

    assert output.brief_title == "Summer Sale Reel"
    assert output.pinned_comments == []
    assert output.hashtags == ["#sale", "#summer", "#neutral"]


def test_generate_script_output_defaults_to_production_rules_provider() -> None:
    brief = PhaseOneDirector().plan(_planned_brief())

    output = generate_script_output(brief)

    assert output.provider_name == "rules_provider"
    assert output.generator_path == "rules_plus_provider"
    assert output.generation_metadata["fallback"] is False
    assert output.hook_text != "Mobility reset for busy professionals who want"


def test_generator_selection_can_force_stub_or_production() -> None:
    assert isinstance(
        build_script_generator(ScriptGeneratorPath.DETERMINISTIC_STUB),
        DeterministicScriptGenerator,
    )
    assert isinstance(
        build_script_generator("rules_plus_provider"), RulesPlusProviderScriptGenerator
    )


def test_schema_compatibility_across_generator_paths() -> None:
    brief = PhaseOneDirector().plan(_planned_brief())

    outputs = [
        generate_script_output(brief, generator_path=ScriptGeneratorPath.DETERMINISTIC_STUB),
        generate_script_output(brief, generator_path=ScriptGeneratorPath.RULES_PLUS_PROVIDER),
    ]

    for output in outputs:
        round_tripped = GeneratedScriptOutput.model_validate(output.model_dump(mode="json"))
        assert round_tripped.schema_version == "phase_1"
        assert round_tripped.hook_text
        assert round_tripped.spoken_script
        assert round_tripped.overlay_timeline
        assert {variant.variant.value for variant in round_tripped.caption_variants} == {
            "short",
            "standard",
            "engagement",
        }
        assert round_tripped.hashtags
        assert round_tripped.pinned_comments
