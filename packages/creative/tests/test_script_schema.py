from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_lab_creative.types import (
    CaptionVariant,
    CaptionVariantName,
    GeneratedScriptOutput,
    OverlayCue,
    ScriptBeat,
    ScriptOverlayEmphasis,
)


def test_generated_script_output_accepts_valid_shape() -> None:
    output = GeneratedScriptOutput(
        provider_name="deterministic_stub",
        brief_title="Northwind Fitness: mobility (explore)",
        duration_seconds=30,
        hook_text="Mobility reset for busy professionals",
        spoken_script=[
            ScriptBeat(
                start_seconds=0,
                end_seconds=10,
                narration="Mobility reset for busy professionals",
            ),
            ScriptBeat(
                start_seconds=10,
                end_seconds=20,
                narration="Set up one practical movement pattern.",
            ),
            ScriptBeat(
                start_seconds=20,
                end_seconds=30,
                narration="End with one clean takeaway.",
            ),
        ],
        overlay_timeline=[
            OverlayCue(
                start_seconds=0,
                end_seconds=10,
                text="Mobility reset",
                emphasis=ScriptOverlayEmphasis.HOOK,
            ),
            OverlayCue(
                start_seconds=10,
                end_seconds=20,
                text="One practical pattern",
                emphasis=ScriptOverlayEmphasis.VALUE,
            ),
            OverlayCue(
                start_seconds=20,
                end_seconds=30,
                text="Clean takeaway",
                emphasis=ScriptOverlayEmphasis.CTA,
            ),
        ],
        caption_variants=[
            CaptionVariant(
                variant=CaptionVariantName.SHORT,
                text="Mobility reset for busy professionals.",
            ),
            CaptionVariant(
                variant=CaptionVariantName.STANDARD,
                text="A practical short-form mobility reel with a clear ending beat.",
            ),
        ],
        hashtags=["#mobility", "#northwindfitness"],
    )

    assert output.schema_version == "phase_1"
    assert output.caption_variants[0].variant is CaptionVariantName.SHORT


def test_generated_script_output_rejects_duplicate_caption_slots() -> None:
    with pytest.raises(ValidationError):
        GeneratedScriptOutput(
            provider_name="deterministic_stub",
            brief_title="Northwind Fitness: mobility (explore)",
            duration_seconds=30,
            hook_text="Mobility reset for busy professionals",
            spoken_script=[
                ScriptBeat(
                    start_seconds=0,
                    end_seconds=15,
                    narration="Mobility reset for busy professionals",
                ),
                ScriptBeat(
                    start_seconds=15,
                    end_seconds=30,
                    narration="End with one clean takeaway.",
                ),
            ],
            overlay_timeline=[
                OverlayCue(
                    start_seconds=0,
                    end_seconds=15,
                    text="Mobility reset",
                ),
            ],
            caption_variants=[
                CaptionVariant(
                    variant=CaptionVariantName.SHORT,
                    text="First version.",
                ),
                CaptionVariant(
                    variant=CaptionVariantName.SHORT,
                    text="Second version.",
                ),
            ],
            hashtags=["#mobility"],
        )


def test_generated_script_output_rejects_invalid_hashtags_and_timeline_bounds() -> None:
    with pytest.raises(ValidationError):
        GeneratedScriptOutput(
            provider_name="deterministic_stub",
            brief_title="Northwind Fitness: mobility (explore)",
            duration_seconds=30,
            hook_text="Mobility reset for busy professionals",
            spoken_script=[
                ScriptBeat(
                    start_seconds=0,
                    end_seconds=15,
                    narration="Mobility reset for busy professionals",
                ),
                ScriptBeat(
                    start_seconds=15,
                    end_seconds=35,
                    narration="End with one clean takeaway.",
                ),
            ],
            overlay_timeline=[
                OverlayCue(
                    start_seconds=0,
                    end_seconds=15,
                    text="Mobility reset",
                ),
            ],
            caption_variants=[
                CaptionVariant(
                    variant=CaptionVariantName.SHORT,
                    text="First version.",
                ),
            ],
            hashtags=["mobility"],
        )
