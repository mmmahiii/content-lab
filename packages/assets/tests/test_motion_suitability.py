from __future__ import annotations

from content_lab_assets.motion_suitability import evaluate_motion_suitability
from content_lab_assets.types import AssetKind, MediaType


def test_prop_image_static_friendly() -> None:
    m = evaluate_motion_suitability(
        asset_kind=AssetKind.PROP_IMAGE,
        media_type=MediaType.IMAGE,
        purpose="Product detail",
        prompt_or_description="Luxury watch on marble surface",
    )
    assert m.static_asset_allowed is True
    assert m.requires_true_motion is False
    assert m.preferred_media_type == "image"


def test_motion_keywords_require_video() -> None:
    m = evaluate_motion_suitability(
        asset_kind=AssetKind.PROP_IMAGE,
        media_type=MediaType.IMAGE,
        purpose="Cooking scene",
        prompt_or_description="Hand stirring food in a pan",
    )
    assert m.requires_true_motion is True
    assert m.static_asset_allowed is False
    assert m.preferred_media_type == "video"


def test_background_video_role() -> None:
    m = evaluate_motion_suitability(
        asset_kind=AssetKind.BACKGROUND_VIDEO,
        media_type=MediaType.VIDEO,
        purpose="Establishing shot",
        prompt_or_description="City skyline at dusk",
    )
    assert m.requires_true_motion is True
    assert m.preferred_media_type == "video"
