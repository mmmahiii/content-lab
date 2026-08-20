from __future__ import annotations

from dataclasses import dataclass

from content_lab_editing.support_surface_overlap import (
    PlacementOverlapArtifacts,
    SupportSurfaceMask,
    resolve_support_overlap_ratio,
    support_overlap_ratio_bbox,
    support_overlap_ratio_mask,
)


@dataclass
class _Obj:
    x: float
    y: float
    scale: float = 1.0
    width_normalised: float = 0.4
    height_normalised: float = 0.4
    source_width: int | None = None
    source_height: int | None = None


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


def test_bbox_overlap_high_while_mask_overlap_is_low() -> None:
    support = _Obj(x=0.5, y=0.5, width_normalised=0.9, height_normalised=0.9)
    # Dependent sits on the support bbox corner (high bbox IoU with support) but away from mask occupancy.
    dependent = _Obj(x=0.14, y=0.14, width_normalised=0.22, height_normalised=0.22)
    mask = _mask(8, 8, filled_center=True)

    bbox_ratio = support_overlap_ratio_bbox(dependent, support)
    mask_ratio = support_overlap_ratio_mask(dependent, support, mask)

    assert bbox_ratio > 0.4
    assert mask_ratio < 0.2


def test_resolve_support_overlap_ratio_uses_mask_when_artifacts_present() -> None:
    support = _Obj(x=0.5, y=0.5, width_normalised=0.9, height_normalised=0.9)
    dependent = _Obj(x=0.14, y=0.14, width_normalised=0.22, height_normalised=0.22)
    mask = _mask(8, 8, filled_center=True)
    artifacts = PlacementOverlapArtifacts(support_surface_mask=mask)

    ratio, method = resolve_support_overlap_ratio(dependent, support, artifacts)

    assert method == "mask"
    assert ratio < 0.2


def test_resolve_support_overlap_ratio_falls_back_to_bbox_without_mask() -> None:
    support = _Obj(x=0.5, y=0.5, width_normalised=0.9, height_normalised=0.9)
    dependent = _Obj(x=0.5, y=0.5, width_normalised=0.2, height_normalised=0.2)

    ratio, method = resolve_support_overlap_ratio(dependent, support, None)

    assert method == "bbox"
    assert ratio > 0.5
