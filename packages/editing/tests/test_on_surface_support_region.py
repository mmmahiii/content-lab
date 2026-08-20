from __future__ import annotations

from dataclasses import dataclass

from content_lab_editing.relationship_layout import enforce_relationship_layout
from content_lab_editing.support_surface_overlap import (
    OverlapValidationContext,
    PlacementOverlapArtifacts,
    SupportSurfaceMask,
    evaluate_on_surface_support_region,
)
from tests.test_relationship_layout import _object, _timeline


@dataclass
class _Support:
    x: float
    y: float
    scale: float = 1.0
    width_normalised: float = 0.9
    height_normalised: float = 0.9
    source_width: int | None = None
    source_height: int | None = None
    asset_id: str = "surface"
    support_surface_mask_uri: str | None = "s3://masks/plate.png"


def _mask(width: int, height: int, *, filled_center: bool) -> SupportSurfaceMask:
    samples: list[float] = []
    for row in range(height):
        for col in range(width):
            if not filled_center:
                samples.append(0.0)
                continue
            cx = (col + 0.5) / width
            cy = (row + 0.5) / height
            samples.append(1.0 if 0.35 <= cx <= 0.65 and 0.35 <= cy <= 0.65 else 0.0)
    return SupportSurfaceMask(width=width, height=height, samples=tuple(samples))


def test_on_surface_mask_failure_when_bbox_would_pass() -> None:
    support = _Support(x=0.5, y=0.5)
    dependent = _Support(
        x=0.14,
        y=0.14,
        width_normalised=0.22,
        height_normalised=0.22,
        asset_id="cutout",
        support_surface_mask_uri=None,
    )
    mask = _mask(8, 8, filled_center=True)
    artifacts = PlacementOverlapArtifacts(support_surface_mask=mask)

    result = evaluate_on_surface_support_region(
        dependent,
        support,
        artifacts,
        required_overlap_ratio=0.2,
    )

    assert result.overlap_method == "mask"
    assert result.bbox_overlap_ratio > 0.2
    assert result.mask_overlap_ratio is not None
    assert result.mask_overlap_ratio < 0.2
    assert result.passed is False
    assert result.failure_code == "on_surface_outside_support_region"


def test_enforce_relationship_layout_blocks_on_surface_outside_mask() -> None:
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
    mask = _mask(8, 8, filled_center=True)
    context = OverlapValidationContext(
        by_mask_uri={
            "s3://masks/plate.png": PlacementOverlapArtifacts(support_surface_mask=mask),
        },
    )

    report = enforce_relationship_layout(_timeline([surface, cutout]), overlap_context=context)

    assert not report.passed
    assert "on_surface_outside_support_region" in report.as_dict()["failure_codes"]


def test_on_surface_without_mask_keeps_bbox_only_behaviour() -> None:
    surface = _object("surface", "environment_base", x=0.2, y=0.2, z=0.05)
    cutout = _object("cutout", "supporting_subject", x=0.8, y=0.8, z=0.7)
    cutout.update(
        {
            "spatial_relationship": "on_surface",
            "support_object_id": "surface",
            "required_overlap_ratio": 0.25,
        }
    )

    report = enforce_relationship_layout(_timeline([surface, cutout]))

    assert not report.passed
    assert "relationship_required_overlap_not_met" in report.as_dict()["failure_codes"]
    assert "on_surface_outside_support_region" not in report.as_dict()["failure_codes"]
