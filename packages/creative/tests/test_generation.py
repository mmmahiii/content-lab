from __future__ import annotations

import copy
import itertools
from typing import Any

import pytest

from content_lab_creative import (
    PlannedCreativeBrief,
    build_script_generator,
    default_script_generator_path,
)
from content_lab_creative.generation import (
    BEAT_OVERLAY_MAX_CHARS,
    HOOK_OVERLAY_MAX_CHARS,
    BranchGenerationRequest,
    BranchSelection,
    CreativePageContext,
    HookCandidate,
    HookGenerationRequest,
    HookMechanism,
    compose_reel,
    fallback_branches,
    generate_branches,
    generate_hooks,
    generate_idea_plan,
    viewer_copy_problems,
)
from content_lab_creative.generation.llm_script import LLMScriptGenerator
from content_lab_creative.persona import PageConstraints
from content_lab_creative.types import ScriptGeneratorPath
from content_lab_intelligence import FakeLLMClient, LLMUnavailableError


def _page(**constraints: Any) -> CreativePageContext:
    return CreativePageContext(
        page_name="Desk Reset",
        handle="deskreset",
        niche="business",
        audience="busy founders",
        content_pillars=["operations"],
        constraints=PageConstraints(**constraints),
    )


def _hook_payload(count: int = 3) -> dict[str, Any]:
    rows = [
        ("curiosity_gap", "The 5-minute habit behind calm Mondays"),
        ("bold_claim", "Your to-do list is the problem"),
        ("direct_question", "Why does Friday feel so chaotic?"),
        ("list_promise", "3 inbox rules worth stealing"),
    ]
    return {
        "hooks": [
            {
                "mechanism": mechanism,
                "overlay_text": overlay,
                "spoken_line": f"{overlay}. Here's what changes.",
                "visual_direction": "Close-up of a cluttered desk being cleared.",
                "payoff_promise": "Show the habit working in one week.",
            }
            for mechanism, overlay in rows[:count]
        ]
    }


def _hook() -> HookCandidate:
    return HookCandidate.model_validate(_hook_payload()["hooks"][0])


def _beat(narration: str, overlay: str, seconds: int = 3) -> dict[str, Any]:
    return {
        "narration": narration,
        "overlay_text": overlay,
        "shot_direction": "Tight shot of the calendar.",
        "seconds": seconds,
    }


def _branch_payload() -> dict[str, Any]:
    return {
        "structure": [
            {
                "option_id": "steps",
                "label": "Three steps",
                "teaser": "The whole system in 15 seconds",
                "beats": [
                    _beat("Block the first hour for one task.", "Block the first hour"),
                    _beat("Batch every reply into two windows.", "Batch your replies"),
                ],
            },
            {
                "option_id": "mistake",
                "label": "The mistake",
                "teaser": "What most founders get wrong",
                "beats": [
                    _beat("Most people start with email.", "Email first? Mistake"),
                    _beat("Start with the hardest task instead.", "Hardest task first", 4),
                ],
            },
        ],
        "energy": [
            {
                "option_id": "calm",
                "label": "Calm",
                "teaser": "Slow and satisfying",
                "pace": "chill",
                "duration_scale": 1.3,
                "music_mood": "soft piano",
            },
            {
                "option_id": "fast",
                "label": "Fast",
                "teaser": "Quick cuts",
                "pace": "punchy",
                "duration_scale": 0.75,
                "music_mood": "driving beat",
            },
        ],
        "ending": [
            {
                "option_id": "result",
                "label": "The result",
                "teaser": "A calmer Monday",
                "style": "reveal",
                "beat": _beat("That's a Monday with room to think.", "Room to think"),
            },
            {
                "option_id": "part2",
                "label": "Part 2?",
                "teaser": "One more rule",
                "style": "cliffhanger",
                "beat": _beat("There's one more rule worth knowing.", "Rule 4 next?"),
            },
        ],
    }


# Hooks -------------------------------------------------------------------------------


def test_generate_hooks_uses_llm_output() -> None:
    client = FakeLLMClient([_hook_payload()])
    result = generate_hooks(
        HookGenerationRequest(page=_page(), topic="calmer Mondays", asset_labels=["desk.png"]),
        client=client,
    )
    assert result.source == "llm"
    assert result.niche == "business"
    assert [h.mechanism for h in result.hooks][0] is HookMechanism.CURIOSITY_GAP
    assert result.usage is not None and result.usage["model"] == "fake-model"
    prompt = client.calls[0].prompt
    assert "Desk Reset" in prompt and "calmer Mondays" in prompt and "desk.png" in prompt
    assert "Niche guidance" in prompt
    assert client.calls[0].schema["properties"]["hooks"]["type"] == "array"


def test_hooks_with_repeated_mechanisms_are_repaired() -> None:
    bad = _hook_payload()
    bad["hooks"][1]["mechanism"] = "curiosity_gap"
    client = FakeLLMClient([bad, _hook_payload()])
    result = generate_hooks(HookGenerationRequest(page=_page()), client=client)
    assert result.source == "llm"
    assert "different mechanism" in client.calls[1].messages[2]["content"]


def test_creator_directions_in_hook_copy_are_rejected() -> None:
    leaky = _hook_payload()
    leaky["hooks"][0]["overlay_text"] = "Open with the exact problem"
    client = FakeLLMClient([leaky, leaky])
    result = generate_hooks(HookGenerationRequest(page=_page()), client=client)
    assert result.source == "fallback"
    assert result.fallback_reason == "LLMOutputError"
    assert "instruction to the creator" in client.calls[1].messages[2]["content"]


def test_blocked_phrases_from_page_constraints_are_enforced() -> None:
    payload = _hook_payload()
    payload["hooks"][1]["overlay_text"] = "Guaranteed results in a week"
    client = FakeLLMClient([payload, _hook_payload()])
    result = generate_hooks(
        HookGenerationRequest(page=_page(prohibited_claims=["guaranteed results"])),
        client=client,
    )
    assert result.source == "llm"
    assert "blocked phrase" in client.calls[1].messages[2]["content"]


def test_wrong_hook_count_is_rejected() -> None:
    client = FakeLLMClient([_hook_payload(count=2), _hook_payload(count=4)])
    result = generate_hooks(HookGenerationRequest(page=_page(), count=4), client=client)
    assert result.source == "llm"
    assert len(result.hooks) == 4
    assert "exactly 4 hooks" in client.calls[1].messages[2]["content"]


def test_hooks_fall_back_without_a_client() -> None:
    result = generate_hooks(
        HookGenerationRequest(page=_page(), topic="morning planning", count=5), client=None
    )
    assert result.source == "fallback"
    assert result.fallback_reason == "llm_not_configured"
    assert len({h.mechanism for h in result.hooks}) == 5
    for hook in result.hooks:
        assert len(hook.overlay_text) <= HOOK_OVERLAY_MAX_CHARS
        assert "morning planning" in hook.overlay_text
        assert viewer_copy_problems(hook.overlay_text, None, overlay=True) == []


def test_hooks_fall_back_when_provider_is_down() -> None:
    result = generate_hooks(
        HookGenerationRequest(page=_page()), client=FakeLLMClient([LLMUnavailableError("503")])
    )
    assert result.source == "fallback"
    assert result.fallback_reason == "LLMUnavailableError"


# Branches ----------------------------------------------------------------------------


def test_generate_branches_returns_options_and_a_preview() -> None:
    client = FakeLLMClient([_branch_payload()])
    result = generate_branches(
        BranchGenerationRequest(page=_page(), hook=_hook(), options_per_moment=2),
        client=client,
    )
    assert result.source == "llm"
    assert result.default_selection == BranchSelection(
        structure="steps", energy="calm", ending="result"
    )
    assert result.preview.overlay_timeline[0].text == _hook().overlay_text
    assert "must pay off" in client.calls[0].prompt


def test_every_branch_combination_composes_into_a_valid_timeline() -> None:
    from content_lab_creative.generation import BranchSet

    branches = BranchSet.model_validate(_branch_payload())
    hook = _hook()
    for structure, energy, ending in itertools.product(
        branches.structure, branches.energy, branches.ending
    ):
        selection = BranchSelection(
            structure=structure.option_id, energy=energy.option_id, ending=ending.option_id
        )
        reel = compose_reel(hook=hook, branches=branches, selection=selection, duration_seconds=15)
        overlays = reel.overlay_timeline
        assert overlays[0].start_seconds == 0
        assert overlays[-1].end_seconds == reel.duration_seconds
        for previous, current in itertools.pairwise(overlays):
            assert previous.end_seconds == current.start_seconds
        assert all(cue.end_seconds - cue.start_seconds >= 2 for cue in overlays[1:])
        assert [cue.emphasis.value for cue in overlays] == (
            ["hook"] + ["value"] * (len(overlays) - 2) + ["cta"]
        )
        assert overlays[-1].text == ending.beat.overlay_text
        assert len(reel.spoken_script) == len(overlays) == len(reel.scenes)
        assert all(len(cue.text) <= HOOK_OVERLAY_MAX_CHARS for cue in overlays)


def test_energy_changes_the_reel_length() -> None:
    from content_lab_creative.generation import BranchSet

    branches = BranchSet.model_validate(_branch_payload())
    calm = compose_reel(
        hook=_hook(),
        branches=branches,
        selection=BranchSelection(structure="steps", energy="calm", ending="result"),
        duration_seconds=15,
    )
    fast = compose_reel(
        hook=_hook(),
        branches=branches,
        selection=BranchSelection(structure="steps", energy="fast", ending="result"),
        duration_seconds=15,
    )
    assert fast.duration_seconds < calm.duration_seconds
    assert fast.overlay_timeline[0].end_seconds == 2  # punchy hook is shorter


def test_required_disclosure_replaces_the_closing_overlay() -> None:
    from content_lab_creative.generation import BranchSet

    reel = compose_reel(
        hook=_hook(),
        branches=BranchSet.model_validate(_branch_payload()),
        selection=BranchSelection(structure="steps", energy="calm", ending="result"),
        constraints=PageConstraints(required_disclosures=["Paid partnership"]),
    )
    assert reel.overlay_timeline[-1].text == "Paid partnership"
    assert reel.overlay_timeline[-1].emphasis.value == "disclosure"
    assert reel.scenes[-1].overlay_role == "disclosure"


def test_unknown_selection_is_rejected() -> None:
    from content_lab_creative.generation import BranchSet

    with pytest.raises(ValueError, match="unknown energy option"):
        compose_reel(
            hook=_hook(),
            branches=BranchSet.model_validate(_branch_payload()),
            selection=BranchSelection(structure="steps", energy="nope", ending="result"),
        )


def test_branch_word_budget_is_enforced() -> None:
    client = FakeLLMClient([_branch_payload(), _branch_payload()])
    result = generate_branches(
        BranchGenerationRequest(
            page=_page(max_script_words=20), hook=_hook(), options_per_moment=2
        ),
        client=client,
    )
    assert result.source == "fallback"
    assert "spoken words" in client.calls[1].messages[2]["content"]


def test_malformed_branch_output_falls_back() -> None:
    client = FakeLLMClient(['{"structure": [', "not json either"])
    result = generate_branches(
        BranchGenerationRequest(page=_page(), hook=_hook(), options_per_moment=2), client=client
    )
    assert result.source == "fallback"
    assert result.fallback_reason == "LLMOutputError"
    assert len(result.branches.structure) == 2


def test_fallback_branches_are_valid_for_every_combination() -> None:
    request = BranchGenerationRequest(page=_page(), hook=_hook(), topic="inbox zero")
    branches = fallback_branches(request)
    assert len(branches.structure) == len(branches.energy) == len(branches.ending) == 3
    for structure, energy, ending in itertools.product(
        branches.structure, branches.energy, branches.ending
    ):
        reel = compose_reel(
            hook=request.hook,
            branches=branches,
            selection=BranchSelection(
                structure=structure.option_id, energy=energy.option_id, ending=ending.option_id
            ),
            duration_seconds=request.duration_seconds,
        )
        assert all(len(cue.text) <= HOOK_OVERLAY_MAX_CHARS for cue in reel.overlay_timeline)
        assert all(len(cue.text) <= BEAT_OVERLAY_MAX_CHARS for cue in reel.overlay_timeline[1:])


# Idea plans --------------------------------------------------------------------------


def _idea_payload() -> dict[str, Any]:
    return {
        "title": "Calm Monday system",
        "angle": "One weekly ritual that makes Mondays calmer.",
        "hook_overlay": "The Sunday habit behind calm Mondays",
        "hook_spoken": "This ten-minute Sunday habit changed my Mondays.",
        "hook_direction": "Notebook on a clean desk, pen already moving.",
        "beats": [
            {
                "label": "Proof",
                "direction": "Overhead of the three-item list.",
                "narration": "Pick the three things Monday must protect.",
                "overlay_text": "Pick three priorities",
                "seconds": 4,
            },
            {
                "label": "Action",
                "direction": "Calendar blocks appearing.",
                "narration": "Then block them before anything else lands.",
                "overlay_text": "Block them first",
                "seconds": 4,
            },
        ],
        "caption_angles": [
            "Ten minutes on Sunday, a calmer Monday.",
            "The weekly ritual I wish I'd started sooner.",
            "What would your three be?",
        ],
    }


def test_idea_plan_from_llm_keeps_directions_and_copy_separate() -> None:
    result = generate_idea_plan(_page(), plan_number=2, client=FakeLLMClient([_idea_payload()]))
    plan = result.plan
    assert result.source == "llm"
    assert plan["hook"] == "The Sunday habit behind calm Mondays"
    assert [beat["label"] for beat in plan["beats"]] == ["Hook", "Proof", "Action"]
    assert plan["beats"][0]["narration"] == "This ten-minute Sunday habit changed my Mondays."
    for beat in plan["beats"]:
        assert beat["overlay_text"] != beat["text"]
    assert plan["generation"]["source"] == "llm"


def test_idea_plan_falls_back_to_template_with_viewer_copy() -> None:
    result = generate_idea_plan(
        _page(), plan_number=3, client=FakeLLMClient([LLMUnavailableError("down")])
    )
    plan = result.plan
    assert result.source == "template"
    assert plan["title"] == "Desk Reset plan 3"
    assert plan["generation"]["fallback_reason"] == "LLMUnavailableError"
    for beat in plan["beats"][1:]:
        assert viewer_copy_problems(beat["overlay_text"], None, overlay=True) == []
        assert viewer_copy_problems(beat["narration"], None) == []


def test_page_context_from_page_metadata() -> None:
    page = CreativePageContext.from_page(
        display_name="Iron Habit",
        handle="ironhabit",
        metadata={
            "niche": "fitness",
            "persona": {"label": "Coach", "audience": "new lifters", "content_pillars": ["form"]},
            "constraints": {"blocked_phrases": ["no pain no gain"]},
            "unrelated": {"kept": "out"},
        },
    )
    assert page.niche == "fitness"
    assert page.audience == "new lifters"
    assert page.niche_profile().key == "fitness"
    assert "no pain no gain" in page.validation_context()["blocked_terms"]


def test_page_context_tolerates_invalid_metadata() -> None:
    page = CreativePageContext.from_page(
        display_name="X", metadata={"persona": {"label": 123, "nonsense": True}}
    )
    assert page.persona_label is None


# Script generator --------------------------------------------------------------------


def _brief(**constraints: Any) -> PlannedCreativeBrief:
    from content_lab_core.types import Platform
    from content_lab_creative.director import PhaseOneDirector
    from content_lab_creative.persona import PageMetadata, PersonaProfile
    from content_lab_creative.types import DirectorPlanInput, PolicyStateDocument

    return PhaseOneDirector().plan(
        DirectorPlanInput(
            page_name="Desk Reset",
            brief_index=0,
            target_platforms=[Platform.INSTAGRAM],
            page_metadata=PageMetadata(
                persona=PersonaProfile(
                    label="Calm operator",
                    audience="busy founders",
                    brand_tone=["direct"],
                    content_pillars=["operations"],
                ),
                constraints=PageConstraints(**constraints),
            ),
            global_policy=PolicyStateDocument(),
        )
    )


def _script_payload() -> dict[str, Any]:
    return {
        "hook_overlay": "The Sunday habit behind calm Mondays",
        "hook_spoken": "This ten-minute habit changed my Mondays.",
        "hook_shot": "Notebook on a clean desk.",
        "beats": [
            {
                "narration": "Write the three things Monday must protect.",
                "overlay_text": "Pick three priorities",
                "shot_direction": "Overhead list.",
            },
            {
                "narration": "Then block them before anything else lands.",
                "overlay_text": "Block them first",
                "shot_direction": "Calendar blocks.",
            },
            {
                "narration": "Ten minutes on Sunday buys you a calm Monday.",
                "overlay_text": "Calm Monday, done",
                "shot_direction": "Hold on the finished week.",
            },
        ],
        "caption_short": "Ten minutes on Sunday, a calmer Monday.",
        "caption_standard": "The weekly ritual that protects your best hours.",
        "caption_engagement": "What would your three be?",
        "hashtags": ["#Productivity", "founders", "productivity", "weekly planning"],
        "pinned_comment": "Want the template? Tell us below.",
    }


def test_llm_script_generator_compiles_pipeline_output() -> None:
    generator = LLMScriptGenerator(client=FakeLLMClient([_script_payload()]))
    output = generator.generate(_brief())
    assert output.generator_path == ScriptGeneratorPath.LLM.value
    assert output.provider_name == "llm:fake-model"
    assert output.hook_text == "The Sunday habit behind calm Mondays"
    assert [cue.emphasis.value for cue in output.overlay_timeline] == [
        "hook",
        "value",
        "value",
        "cta",
    ]
    assert output.overlay_timeline[-1].end_seconds == output.duration_seconds
    assert output.hashtags == ["#productivity", "#founders", "#weeklyplanning"]
    assert output.generation_metadata["creative_lint"]["outcome"] != "fail"
    assert output.generation_metadata["usage"]["model"] == "fake-model"


def test_llm_script_generator_appends_disclosures() -> None:
    brief = _brief(required_disclosures=["Includes an affiliate link"])
    output = LLMScriptGenerator(client=FakeLLMClient([_script_payload()])).generate(brief)
    assert output.overlay_timeline[-1].text == "Includes an affiliate link"
    assert all("affiliate link" in caption.text for caption in output.caption_variants)


def test_llm_script_generator_falls_back_on_failure() -> None:
    generator = LLMScriptGenerator(client=FakeLLMClient([LLMUnavailableError("timeout")]))
    output = generator.generate(_brief())
    assert output.generator_path == ScriptGeneratorPath.RULES_PLUS_PROVIDER.value
    assert output.generation_metadata["llm_fallback_reason"] == "LLMUnavailableError"


def test_llm_script_generator_without_client_uses_rules() -> None:
    output = LLMScriptGenerator(use_env_client=False).generate(_brief())
    assert output.generation_metadata["llm_fallback_reason"] == "llm_not_configured"


def test_malformed_script_output_falls_back() -> None:
    bad = copy.deepcopy(_script_payload())
    bad["beats"] = bad["beats"][:1]
    output = LLMScriptGenerator(client=FakeLLMClient([bad, "garbage"])).generate(_brief())
    assert output.generation_metadata["llm_fallback_reason"] == "LLMOutputError"


def test_default_generator_path_follows_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONTENT_LAB_SCRIPT_GENERATOR", raising=False)
    assert default_script_generator_path() is ScriptGeneratorPath.RULES_PLUS_PROVIDER
    assert type(build_script_generator()).__name__ == "RulesPlusProviderScriptGenerator"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert default_script_generator_path() is ScriptGeneratorPath.LLM
    assert isinstance(build_script_generator(), LLMScriptGenerator)
    monkeypatch.setenv("CONTENT_LAB_SCRIPT_GENERATOR", "deterministic_stub")
    assert type(build_script_generator()).__name__ == "DeterministicScriptGenerator"
    monkeypatch.setenv("CONTENT_LAB_LLM_PROVIDER", "none")
    monkeypatch.delenv("CONTENT_LAB_SCRIPT_GENERATOR")
    assert default_script_generator_path() is ScriptGeneratorPath.RULES_PLUS_PROVIDER


def test_idea_plan_rejects_narration_that_cannot_fill_its_beat() -> None:
    """Short narration on a long beat was voiced as ~2 s of speech and ~6 s of dead air."""

    from content_lab_creative.generation.idea_plan import IdeaBeatDraft, narration_word_range

    payload = _idea_payload()
    payload["beats"][0]["seconds"] = 8  # 7 words cannot carry an 8 s beat
    retry = _idea_payload()
    result = generate_idea_plan(_page(), plan_number=2, client=FakeLLMClient([payload, retry]))

    assert result.source == "llm"
    assert result.plan["beats"][1]["seconds"] == 4  # the retried, well-sized plan was used
    assert narration_word_range(6) == (9, 21)
    with pytest.raises(ValueError, match="should be 12-28 words"):
        IdeaBeatDraft.model_validate(
            {"label": "Proof", "direction": "d", "narration": "Too short.",
             "overlay_text": "Short", "seconds": 8}
        )  # fmt: skip


def test_template_idea_plan_narration_fits_each_beat() -> None:
    from content_lab_creative.generation.idea_plan import narration_word_range

    result = generate_idea_plan(
        _page(), plan_number=3, client=FakeLLMClient([LLMUnavailableError("down")])
    )

    for beat in result.plan["beats"][1:]:
        low, high = narration_word_range(int(beat["seconds"]))
        assert low <= len(beat["narration"].split()) <= high, beat
