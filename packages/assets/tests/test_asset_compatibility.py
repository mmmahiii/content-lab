from __future__ import annotations

from content_lab_assets.compatibility import AssetCompatibilityMetadata, compatibility_score
from content_lab_assets.metadata import derive_asset_compatibility_metadata
from content_lab_assets.types import AssetKind


def test_low_resolution_background_image_receives_low_resolution_class() -> None:
    metadata = derive_asset_compatibility_metadata(
        asset_kind=AssetKind.BACKGROUND_IMAGE,
        transparency=False,
        width=480,
        height=854,
        possible_cinematic_roles=["environment_base"],
    )

    assert metadata.asset_resolution_class == "low"


def test_low_resolution_environment_is_not_full_frame_base_without_override() -> None:
    metadata = derive_asset_compatibility_metadata(
        asset_kind=AssetKind.BACKGROUND_IMAGE,
        transparency=False,
        width=640,
        height=640,
        possible_cinematic_roles=["environment_base"],
    )

    assert metadata.can_be_full_frame_base is False


def test_transparent_cutout_requires_support_by_default() -> None:
    metadata = derive_asset_compatibility_metadata(
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        transparency=True,
        width=1200,
        height=1200,
        possible_cinematic_roles=["supporting_subject", "foreground_texture"],
    )

    assert metadata.can_be_supported_by_surface is True


def test_background_reveal_prefers_rear_screen_regions() -> None:
    metadata = derive_asset_compatibility_metadata(
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        transparency=True,
        width=900,
        height=900,
        possible_cinematic_roles=["background_reveal"],
    )

    assert "foreground" not in metadata.preferred_screen_regions
    assert "upper_right" in metadata.preferred_screen_regions
    assert "rear" in metadata.preferred_screen_regions
    assert metadata.can_support_objects is False
    assert metadata.alpha_quality == "clean"


def test_horizontal_surface_plane_is_compatible_with_supported_objects() -> None:
    surface = AssetCompatibilityMetadata(
        surface_plane="horizontal",
        view_angle="top_down",
        can_support_objects=True,
        compatible_view_angles=["top_down", "overhead"],
    )
    prop = AssetCompatibilityMetadata(
        surface_plane="unknown",
        view_angle="top_down",
        can_be_supported_by_surface=True,
    )

    result = compatibility_score(surface, prop)

    assert result.score >= 0.7
    assert result.verdict in {"pass", "warn"}


def test_front_facing_asset_warns_when_combined_with_top_down_base() -> None:
    base = AssetCompatibilityMetadata(
        surface_plane="horizontal",
        view_angle="top_down",
        can_support_objects=True,
    )
    front_asset = AssetCompatibilityMetadata(
        view_angle="front",
        can_be_supported_by_surface=True,
    )

    result = compatibility_score(base, front_asset)

    assert result.verdict == "warn"
    assert any("view angle" in warning for warning in result.warnings)


def test_unknown_metadata_increases_risk_without_crashing() -> None:
    result = compatibility_score(AssetCompatibilityMetadata(), AssetCompatibilityMetadata())

    assert result.score > 0
    assert any("unknown metadata" in warning for warning in result.warnings)


def test_compatibility_score_returns_lower_score_for_mismatched_view_angles() -> None:
    base = AssetCompatibilityMetadata(
        surface_plane="horizontal",
        view_angle="top_down",
        can_support_objects=True,
    )
    matched = AssetCompatibilityMetadata(
        view_angle="top_down",
        can_be_supported_by_surface=True,
    )
    mismatched = AssetCompatibilityMetadata(
        view_angle="front",
        can_be_supported_by_surface=True,
    )

    assert compatibility_score(base, mismatched).score < compatibility_score(base, matched).score
