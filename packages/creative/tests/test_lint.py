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
    assert {f.category for f in result.findings if f.category} == {"meta_generation_language"}


def test_lint_rejects_current_bad_incomplete_hook_example() -> None:
    result = lint_script_output(
        _script_output(hook_text="Mobility reset for busy professionals who want")
    )

    assert result.outcome == "fail"
    assert any(finding.code == "incomplete_hook" for finding in result.findings)


def test_lint_caption_hard_fails_planner_metalanguage_cap_d001() -> None:
    """Regression: model sometimes echoed plan/test labels into the caption line."""
    bug_caption = (
        "Create a explore reel for Smoke Test Page focused on operations for Busy founders..."
    )
    result = lint_script_output(_script_output(caption_text=bug_caption))

    assert result.outcome == "fail"
    caption_failures = [
        f
        for f in result.findings
        if f.outcome == "fail" and f.field_path == "caption_variants[0].text"
    ]
    assert caption_failures
    matched = {f.matched_phrase for f in caption_failures}
    assert "Create a" in matched
    assert "reel for" in matched
    assert "Smoke Test Page" in matched
    assert "focused on" in matched
    assert "explore" in matched
    by_cat = {f.category: f for f in caption_failures if f.category}
    assert "test_scaffold_language" in by_cat
    assert "Smoke Test Page" in by_cat["test_scaffold_language"].matched_phrase


def test_lint_allows_d001_patterns_outside_caption() -> None:
    """Caption-only rules: same tokens in spoken script must not use caption code paths."""
    result = lint_script_output(
        _script_output(
            spoken_script=[
                ScriptBeat(
                    start_seconds=0,
                    end_seconds=20,
                    narration="We explore a simple plan and stay focused on what matters for founders.",
                ),
            ],
        )
    )
    assert not any(f.code.startswith("caption_meta_") for f in result.findings)


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
    assert all(
        f.category == "meta_generation_language"
        for f in result.findings
        if f.code == "abstract_script_language"
    )


def test_lint_passes_specific_viewer_facing_script() -> None:
    result = lint_script_output(_script_output())

    assert result.outcome == "pass"
    assert result.passed is True
    assert result.findings == []
