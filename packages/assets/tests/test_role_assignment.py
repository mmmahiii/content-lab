from __future__ import annotations

from content_lab_assets.role_assignment import (
    cinematic_roles_for_asset,
    normalize_asset_for_cinematic_planning,
)


def test_normalize_asset_assigns_environment_and_prompt_safe_metadata() -> None:
    descriptor = normalize_asset_for_cinematic_planning(
        {
            "asset_id": "kitchen_bg",
            "asset_kind": "background_video",
            "pack_role": "background",
            "metadata": {
                "title": "Warm kitchen background",
                "description": "window-lit cooking counter",
                "width": 1080,
                "height": 1920,
                "tags": ["kitchen", "warm", 42],
                "transparency": {"has_transparency": True},
                "secret_operator_note": "do not leak",
            },
        }
    )

    assert descriptor.asset_id == "kitchen_bg"
    assert descriptor.media_type == "video"
    assert "environment_base" in descriptor.possible_cinematic_roles
    assert "background_reveal" in descriptor.possible_cinematic_roles
    assert descriptor.transparent is True
    assert descriptor.width == 1080
    assert descriptor.height == 1920
    assert descriptor.tags == ["kitchen", "warm", "42"]
    assert "secret_operator_note" not in descriptor.metadata


def test_cinematic_roles_cover_subject_effect_and_audio_assets() -> None:
    assert "hero_subject" in cinematic_roles_for_asset(
        asset_kind="subject_video",
        media_type="video",
        pack_role="hero",
        metadata={"description": "steak hero closeup"},
    )
    assert "atmospheric_layer" in cinematic_roles_for_asset(
        asset_kind="effect_video",
        media_type="video",
        pack_role="steam overlay",
        metadata={},
    )
    assert cinematic_roles_for_asset(
        asset_kind="sound_effect",
        media_type="audio",
        pack_role="sizzle audio",
        metadata={},
    ) == ("audio_layer",)
