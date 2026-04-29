from __future__ import annotations

from content_lab_creative.lint import lint_script_output
from content_lab_creative.types import (
    CaptionVariant,
    CaptionVariantName,
    GeneratedScriptOutput,
    OverlayCue,
    ScriptBeat,
    ScriptOverlayEmphasis,
)


def _script_output(
    *,
    hook_text: str = "The mobility reset busy professionals can do today",
    spoken_script: list[ScriptBeat] | None = None,
    caption_text: str = "Try this before your next meeting.",
) -> GeneratedScriptOutput:
    return GeneratedScriptOutput(
        provider_name="test_provider",
        generator_path="rules_plus_provider",
        brief_title="Mobility reset",
        duration_seconds=20,
        hook_text=hook_text,
        spoken_script=spoken_script
        or [
            ScriptBeat(start_seconds=0, end_seconds=5, narration=hook_text),
            ScriptBeat(
                start_seconds=5,
                end_seconds=10,
                narration="Busy days can make your hips and shoulders feel stuck.",
            ),
            ScriptBeat(
                start_seconds=10,
                end_seconds=15,
                narration="Try one slow reset and breathe through the tight point.",
            ),
            ScriptBeat(
                start_seconds=15,
                end_seconds=20,
                narration="Save the move for the next time stiffness shows up.",
            ),
        ],
        overlay_timeline=[
            OverlayCue(
                start_seconds=0,
                end_seconds=5,
                text=hook_text,
                emphasis=ScriptOverlayEmphasis.HOOK,
            ),
        ],
        caption_variants=[
            CaptionVariant(
                variant=CaptionVariantName.SHORT,
                text=caption_text,
            ),
        ],
        hashtags=["#mobility"],
    )


def test_lint_rejects_stub_style_meta_language() -> None:
    output = _script_output(
        spoken_script=[
            ScriptBeat(
                start_seconds=0,
                end_seconds=10,
                narration="Set up the core mobility idea for busy professionals with one plain-language step.",
            ),
            ScriptBeat(
                start_seconds=10,
                end_seconds=20,
                narration="Show the useful proof point before the viewer can scroll away.",
            ),
        ]
    )

    result = lint_script_output(output)

    assert result.outcome == "fail"
    assert {finding.code for finding in result.findings} >= {
        "meta_plain_language_step",
        "meta_setup_instruction",
    }


def test_lint_rejects_current_bad_incomplete_hook_example() -> None:
    result = lint_script_output(
        _script_output(hook_text="Mobility reset for busy professionals who want")
    )

    assert result.outcome == "fail"
    assert any(finding.code == "incomplete_hook" for finding in result.findings)


def test_lint_rejects_cta_only_weak_scripts() -> None:
    result = lint_script_output(
        _script_output(
            hook_text="Follow for more",
            spoken_script=[
                ScriptBeat(start_seconds=0, end_seconds=7, narration="Follow for more"),
                ScriptBeat(start_seconds=7, end_seconds=14, narration="Save and share this"),
                ScriptBeat(start_seconds=14, end_seconds=20, narration="Link in bio"),
            ],
        )
    )

    assert result.outcome == "fail"
    assert any(finding.code == "cta_only_script" for finding in result.findings)


def test_lint_warns_on_abstract_but_non_blocking_language() -> None:
    result = lint_script_output(
        _script_output(caption_text="Keep the proof beat simple and memorable.")
    )

    assert result.outcome == "warn"
    assert result.passed is True
    assert any(finding.code == "abstract_script_language" for finding in result.findings)


def test_lint_passes_specific_viewer_facing_script() -> None:
    result = lint_script_output(_script_output())

    assert result.outcome == "pass"
    assert result.passed is True
    assert result.findings == []


BAD_CAPTION_G004 = (
    "Create a explore reel for Smoke Test Page focused on operations for Busy founders."
)
GOOD_CAPTION_STANDARD_G004 = (
    "Founders batch vendor comms into one weekly block so approvals stay in one thread."
)


def test_g004_lint_fails_exact_bad_internal_standard_caption() -> None:
    output = GeneratedScriptOutput(
        provider_name="fixture",
        generator_path="fixture",
        brief_title="Operations",
        duration_seconds=12,
        hook_text="Founders can tighten weekly operations without hiring another ops lead.",
        spoken_script=[
            ScriptBeat(start_seconds=0, end_seconds=6, narration="Block two hours on Monday."),
            ScriptBeat(
                start_seconds=6,
                end_seconds=12,
                narration="Reuse the checklist so approvals stop bouncing between Slack threads.",
            ),
        ],
        overlay_timeline=[
            OverlayCue(
                start_seconds=0,
                end_seconds=3,
                text="Batch vendor mail",
                emphasis=ScriptOverlayEmphasis.HOOK,
            ),
        ],
        caption_variants=[
            CaptionVariant(variant=CaptionVariantName.SHORT, text="One ops habit."),
            CaptionVariant(variant=CaptionVariantName.STANDARD, text=BAD_CAPTION_G004),
        ],
        hashtags=["#operations"],
    )
    result = lint_script_output(output)
    assert result.outcome == "fail"
    assert any(f.code == "internal_qa_copy" for f in result.findings)


def test_g004_lint_passes_viewer_ready_standard_caption_positive() -> None:
    output = GeneratedScriptOutput(
        provider_name="fixture",
        generator_path="fixture",
        brief_title="Operations",
        duration_seconds=12,
        hook_text="Founders can tighten weekly operations without hiring another ops lead.",
        spoken_script=[
            ScriptBeat(start_seconds=0, end_seconds=6, narration="Block two hours on Monday."),
            ScriptBeat(
                start_seconds=6,
                end_seconds=12,
                narration="Reuse the checklist so approvals stop bouncing between Slack threads.",
            ),
        ],
        overlay_timeline=[
            OverlayCue(
                start_seconds=0,
                end_seconds=3,
                text="Batch vendor mail",
                emphasis=ScriptOverlayEmphasis.HOOK,
            ),
        ],
        caption_variants=[
            CaptionVariant(variant=CaptionVariantName.SHORT, text="One ops habit."),
            CaptionVariant(variant=CaptionVariantName.STANDARD, text=GOOD_CAPTION_STANDARD_G004),
        ],
        hashtags=["#operations"],
    )
    result = lint_script_output(output)
    assert result.outcome == "pass"
    assert result.findings == []
