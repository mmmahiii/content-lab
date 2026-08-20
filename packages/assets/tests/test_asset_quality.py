from __future__ import annotations

from content_lab_assets.metadata import derive_asset_compatibility_metadata
from content_lab_assets.quality import score_full_frame_quality
from content_lab_assets.types import AssetKind


def test_low_resolution_environment_quality_is_not_full_frame_safe() -> None:
    metadata = derive_asset_compatibility_metadata(
        asset_kind=AssetKind.BACKGROUND_IMAGE,
        transparency=False,
        width=480,
        height=854,
        possible_cinematic_roles=["environment_base"],
    )

    quality = score_full_frame_quality(metadata)

    assert quality.can_use_full_frame is False
    assert any("low-resolution" in warning for warning in quality.warnings)


def test_recommended_max_scale_is_lower_for_low_resolution_assets() -> None:
    low = derive_asset_compatibility_metadata(
        asset_kind=AssetKind.PROP_IMAGE,
        transparency=False,
        width=400,
        height=400,
        possible_cinematic_roles=["supporting_subject"],
    )
    high = derive_asset_compatibility_metadata(
        asset_kind=AssetKind.PROP_IMAGE,
        transparency=False,
        width=1800,
        height=2400,
        possible_cinematic_roles=["supporting_subject"],
    )

    assert low.recommended_max_scale < high.recommended_max_scale
