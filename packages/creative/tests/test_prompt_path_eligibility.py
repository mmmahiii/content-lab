from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_lab_creative.prompt_path_eligibility import (
    PromptPathEligibilityGate,
    aggregate_prompt_path_capabilities,
    validate_prompt_paths_allowed_for_assets,
)
from content_lab_creative.single_prompt_reel_planner import SinglePromptPlannerInput


def _static_png_asset(asset_id: str = "a1", **kwargs: object) -> dict[str, object]:
    base: dict[str, object] = {
        "asset_id": asset_id,
        "asset_label": "Jar",
        "asset_kind": "transparent_cutout_png",
        "media_type": "image",
        "possible_cinematic_roles": ["hero_subject"],
    }
    base.update(kwargs)
    return base


def test_static_png_only_blocks_sensory_hook_without_placeholder() -> None:
    assets = [_static_png_asset("x"), _static_png_asset("y", asset_label="Spoon")]
    gate = PromptPathEligibilityGate.from_selected_assets(assets)
    assert gate.is_allowed("cinematic_closeup")
    assert gate.is_allowed("object_story")
    assert not gate.is_allowed("sensory_hook")
    assert not gate.is_allowed("speed_ramp_showcase")


def test_placeholder_override_allows_sensory_hook() -> None:
    assets = [
        _static_png_asset(
            "x",
            compatibility={"allow_sensory_placeholder_without_motion_evidence": True},
        )
    ]
    gate = PromptPathEligibilityGate.from_selected_assets(assets)
    assert gate.is_allowed("sensory_hook")


def test_audio_enables_sensory_hook() -> None:
    assets = [
        _static_png_asset("x"),
        {
            "asset_id": "snd",
            "asset_kind": "sound_effect",
            "media_type": "audio",
            "possible_cinematic_roles": ["audio_layer"],
        },
    ]
    gate = PromptPathEligibilityGate.from_selected_assets(assets)
    assert gate.is_allowed("sensory_hook")


def test_video_enables_sensory_hook_and_speed_ramp() -> None:
    assets = [
        {
            "asset_id": "v",
            "asset_kind": "subject_video",
            "media_type": "video",
            "possible_cinematic_roles": ["hero_subject"],
        }
    ]
    gate = PromptPathEligibilityGate.from_selected_assets(assets)
    assert gate.is_allowed("sensory_hook")
    assert gate.is_allowed("speed_ramp_showcase")


def test_atmospheric_overlay_enables_sensory_hook() -> None:
    assets = [
        {
            "asset_id": "steam",
            "asset_kind": "effect_image",
            "media_type": "image",
            "possible_cinematic_roles": ["atmospheric_layer"],
        }
    ]
    gate = PromptPathEligibilityGate.from_selected_assets(assets)
    assert gate.is_allowed("sensory_hook")


def test_two_prep_labeled_assets_enable_satisfying_process() -> None:
    assets = [
        _static_png_asset("a", asset_label="Prep mise step one"),
        _static_png_asset("b", asset_label="Prep mise step two"),
    ]
    agg = aggregate_prompt_path_capabilities(assets)
    assert agg.satisfying_process_evidence is True
    assert not agg.sensory_hook_evidence


def test_pinned_sensory_hook_raises_for_static_pack() -> None:
    with pytest.raises(ValidationError, match="not eligible"):
        SinglePromptPlannerInput(
            page_context={},
            selected_assets=[_static_png_asset()],
            pinned_prompt_paths=["sensory_hook"],
        )


def test_validate_prompt_paths_allowed_for_assets_raises() -> None:
    assets = [_static_png_asset()]
    with pytest.raises(ValueError, match="not eligible"):
        validate_prompt_paths_allowed_for_assets(["sensory_hook"], assets=assets)
