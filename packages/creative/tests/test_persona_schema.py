from __future__ import annotations

import pytest

from content_lab_creative.persona import PageMetadata, validate_persona_profile


def test_persona_profile_normalizes_phase_one_fields_and_extensions() -> None:
    persona = validate_persona_profile(
        {
            "label": "  Calm educator  ",
            "audience": "  Busy founders  ",
            "brand_tone": ["clear", "Clear", "grounded"],
            "content_pillars": ["operations", "Operations", "positioning"],
            "differentiators": ["operator-led advice"],
            "primary_call_to_action": "  Book a strategy call  ",
            "extensions": {
                "Voice": "  plainspoken and specific  ",
                "banned-motifs": ["stock trading charts", "Stock Trading Charts"],
                "cta posture": "  soft_sell  ",
            },
        }
    )

    assert persona.label == "Calm educator"
    assert persona.audience == "Busy founders"
    assert persona.brand_tone == ["clear", "grounded"]
    assert persona.content_pillars == ["operations", "positioning"]
    assert persona.primary_call_to_action == "Book a strategy call"
    assert persona.extensions == {
        "voice": "plainspoken and specific",
        "banned_motifs": ["stock trading charts"],
        "cta_posture": "soft_sell",
    }


def test_persona_profile_rejects_missing_required_phase_one_fields() -> None:
    with pytest.raises(Exception, match="content_pillars must contain at least one item"):
        validate_persona_profile(
            {
                "label": "Helpful brand",
                "audience": "Creators",
                "content_pillars": [],
            }
        )


def test_page_metadata_rejects_invalid_extension_values() -> None:
    with pytest.raises(Exception, match="extensions values must be strings or arrays of strings"):
        PageMetadata.model_validate(
            {
                "persona": {
                    "label": "Helpful brand",
                    "audience": "Creators",
                    "content_pillars": ["education"],
                    "extensions": {"voice": {"style": "warm"}},
                }
            }
        )
