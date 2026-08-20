from __future__ import annotations

from content_lab_editing.compositor import preflight_compositor_timeline
from content_lab_editing.support_surface_overlap import (
    OverlapValidationContext,
    PlacementOverlapArtifacts,
    SupportSurfaceMask,
)
from tests.test_relationship_layout import _object, _timeline
from tests.test_on_surface_support_region import _mask


def test_renderer_blocks_floating_supported_cutout() -> None:
    surface = _object("surface", "environment_base", x=0.2, y=0.2, z=0.05)
    cutout = _object("cutout", "supporting_subject", x=0.8, y=0.8, z=0.7)
    cutout.update(
        {
            "spatial_relationship": "on_surface",
            "support_object_id": "surface",
            "required_overlap_ratio": 0.2,
        }
    )

    report = preflight_compositor_timeline(_timeline([surface, cutout]).model_dump(mode="json"))

    assert not report.passed
    assert (
        "relationship_required_overlap_not_met"
        in report.relationship_layout.as_dict()["failure_codes"]
    )


def test_renderer_accepts_valid_supported_asset_led_layout() -> None:
    surface = _object("surface", "environment_base", x=0.5, y=0.5, z=0.05)
    surface["width_normalised"] = 0.9
    surface["height_normalised"] = 0.8
    hero = _object("hero", "hero_subject", x=0.5, y=0.5, z=0.7)
    hero.update(
        {
            "spatial_relationship": "on_surface",
            "support_object_id": "surface",
            "required_overlap_ratio": 0.1,
            "support_contact_required": True,
            "contact_shadow_target_object_id": "surface",
            "relative_depth_rule": "above_support",
            "shadow_spec": {"contact_shadow_required": True},
        }
    )

    report = preflight_compositor_timeline(_timeline([surface, hero]).model_dump(mode="json"))

    assert report.passed is True


def test_preflight_blocks_on_surface_outside_support_mask() -> None:
    surface = _object("surface", "environment_base", x=0.5, y=0.5, z=0.05)
    surface["width_normalised"] = 0.9
    surface["height_normalised"] = 0.9
    surface["support_surface_mask_uri"] = "s3://masks/plate.png"
    cutout = _object("cutout", "supporting_subject", x=0.14, y=0.14, z=0.7)
    cutout.update(
        {
            "spatial_relationship": "on_surface",
            "support_object_id": "surface",
            "required_overlap_ratio": 0.2,
        }
    )
    context = OverlapValidationContext(
        by_mask_uri={
            "s3://masks/plate.png": PlacementOverlapArtifacts(
                support_surface_mask=_mask(8, 8, filled_center=True),
            ),
        },
    )

    report = preflight_compositor_timeline(
        _timeline([surface, cutout]).model_dump(mode="json"),
        overlap_context=context,
    )

    assert not report.passed
    assert "on_surface_outside_support_region" in report.relationship_layout.as_dict()["failure_codes"]
