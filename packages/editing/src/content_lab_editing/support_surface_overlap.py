"""Support-surface mask overlap for timeline object placement."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Protocol

from content_lab_editing.bounds import normalized_bounds, overlap_ratio

_DEFAULT_SAMPLE_GRID = 32
_DEFAULT_ALPHA_THRESHOLD = 0.5


class SupportOverlapObject(Protocol):
    x: float
    y: float
    scale: float
    width_normalised: float
    height_normalised: float
    source_width: int | None
    source_height: int | None


@dataclass(frozen=True, slots=True)
class SupportSurfaceMask:
    """Grayscale support-surface occupancy in normalized asset UV space."""

    width: int
    height: int
    samples: tuple[float, ...]

    def __post_init__(self) -> None:
        expected = self.width * self.height
        if len(self.samples) != expected:
            raise ValueError(f"mask sample count {len(self.samples)} != {expected}")

    def sample(self, u: float, v: float) -> float:
        if self.width <= 0 or self.height <= 0:
            return 0.0
        u_clamped = min(1.0, max(0.0, u))
        v_clamped = min(1.0, max(0.0, v))
        col = min(self.width - 1, int(u_clamped * self.width))
        row = min(self.height - 1, int(v_clamped * self.height))
        return self.samples[row * self.width + col]


@dataclass(frozen=True, slots=True)
class PlacementOverlapArtifacts:
    """Resolved placement overlap inputs for one registry asset."""

    support_surface_mask: SupportSurfaceMask | None = None
    intrinsic_width: int | None = None
    intrinsic_height: int | None = None


@dataclass(frozen=True, slots=True)
class OverlapValidationContext:
    """Pre-resolved masks for QA and renderer overlap checks."""

    by_asset_id: Mapping[str, PlacementOverlapArtifacts] = field(default_factory=dict)
    by_mask_uri: Mapping[str, PlacementOverlapArtifacts] = field(default_factory=dict)


class SupportOverlapTimelineObject(Protocol):
    asset_id: str
    support_surface_mask_uri: str | None


def overlap_artifacts_for_support(
    support: SupportOverlapTimelineObject,
    context: OverlapValidationContext | None,
) -> PlacementOverlapArtifacts | None:
    if context is None:
        return None
    override_uri = support.support_surface_mask_uri
    if override_uri:
        artifacts = context.by_mask_uri.get(override_uri)
        if artifacts is not None:
            return artifacts
    return context.by_asset_id.get(support.asset_id)


def support_overlap_ratio_bbox(dependent: SupportOverlapObject, support: SupportOverlapObject) -> float:
    """BBox overlap ratio of dependent footprint (legacy default)."""

    return overlap_ratio(dependent, support)


def support_overlap_ratio_mask(
    dependent: SupportOverlapObject,
    support: SupportOverlapObject,
    mask: SupportSurfaceMask,
    *,
    intrinsic_width: int | None = None,
    intrinsic_height: int | None = None,
    alpha_threshold: float = _DEFAULT_ALPHA_THRESHOLD,
    sample_grid: int = _DEFAULT_SAMPLE_GRID,
) -> float:
    """Fraction of dependent footprint samples that hit occupied support-surface mask pixels."""

    dep_bounds = normalized_bounds(dependent)
    if dep_bounds.area <= 0.0:
        return 0.0

    sup_bounds = normalized_bounds(support)
    if sup_bounds.width <= 0.0 or sup_bounds.height <= 0.0:
        return 0.0

    width = max(2, sample_grid)
    height = max(2, sample_grid)
    hits = 0
    total = 0
    for row in range(height):
        for col in range(width):
            cx = dep_bounds.left + ((col + 0.5) / width) * dep_bounds.width
            cy = dep_bounds.top + ((row + 0.5) / height) * dep_bounds.height
            total += 1
            if not _point_in_bounds(cx, cy, sup_bounds.left, sup_bounds.top, sup_bounds.right, sup_bounds.bottom):
                continue
            u, v = _canvas_to_mask_uv(
                cx,
                cy,
                sup_bounds.left,
                sup_bounds.top,
                sup_bounds.right,
                sup_bounds.bottom,
                intrinsic_width=intrinsic_width or support.source_width,
                intrinsic_height=intrinsic_height or support.source_height,
            )
            if mask.sample(u, v) >= alpha_threshold:
                hits += 1
    return hits / max(1, total)


@dataclass(frozen=True, slots=True)
class OnSurfaceSupportRegionResult:
    """Outcome of on_surface placement vs support-surface mask occupancy."""

    passed: bool
    failure_code: str | None
    bbox_overlap_ratio: float
    mask_overlap_ratio: float | None
    overlap_method: str
    mask_available: bool
    mask_expected: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failure_code": self.failure_code,
            "bbox_overlap_ratio": round(self.bbox_overlap_ratio, 4),
            "mask_overlap_ratio": (
                None if self.mask_overlap_ratio is None else round(self.mask_overlap_ratio, 4)
            ),
            "overlap_method": self.overlap_method,
            "mask_available": self.mask_available,
            "mask_expected": self.mask_expected,
        }


def evaluate_on_surface_support_region(
    dependent: SupportOverlapObject,
    support: SupportOverlapObject | SupportOverlapTimelineObject,
    artifacts: PlacementOverlapArtifacts | None,
    *,
    required_overlap_ratio: float,
    alpha_threshold: float = _DEFAULT_ALPHA_THRESHOLD,
) -> OnSurfaceSupportRegionResult:
    """Check whether a dependent on_surface object sits on occupied support-surface pixels."""

    bbox_overlap = support_overlap_ratio_bbox(dependent, support)
    mask_expected = bool(getattr(support, "support_surface_mask_uri", None))
    mask = None if artifacts is None else artifacts.support_surface_mask
    if mask is not None:
        mask_overlap = support_overlap_ratio_mask(
            dependent,
            support,
            mask,
            intrinsic_width=artifacts.intrinsic_width if artifacts else None,
            intrinsic_height=artifacts.intrinsic_height if artifacts else None,
            alpha_threshold=alpha_threshold,
        )
        passed = mask_overlap >= required_overlap_ratio
        return OnSurfaceSupportRegionResult(
            passed=passed,
            failure_code=None if passed else "on_surface_outside_support_region",
            bbox_overlap_ratio=bbox_overlap,
            mask_overlap_ratio=mask_overlap,
            overlap_method="mask",
            mask_available=True,
            mask_expected=mask_expected,
        )
    passed = bbox_overlap >= required_overlap_ratio
    return OnSurfaceSupportRegionResult(
        passed=passed,
        failure_code=None if passed else "relationship_required_overlap_not_met",
        bbox_overlap_ratio=bbox_overlap,
        mask_overlap_ratio=None,
        overlap_method="bbox",
        mask_available=False,
        mask_expected=mask_expected,
    )


def resolve_support_overlap_ratio(
    dependent: SupportOverlapObject,
    support: SupportOverlapObject,
    artifacts: PlacementOverlapArtifacts | None,
    *,
    alpha_threshold: float = _DEFAULT_ALPHA_THRESHOLD,
) -> tuple[float, str]:
    """Return overlap ratio and method label (``bbox`` or ``mask``)."""

    if artifacts is not None and artifacts.support_surface_mask is not None:
        ratio = support_overlap_ratio_mask(
            dependent,
            support,
            artifacts.support_surface_mask,
            intrinsic_width=artifacts.intrinsic_width,
            intrinsic_height=artifacts.intrinsic_height,
            alpha_threshold=alpha_threshold,
        )
        return ratio, "mask"
    return support_overlap_ratio_bbox(dependent, support), "bbox"


def support_mask_centroid_canvas(
    support: SupportOverlapObject,
    mask: SupportSurfaceMask,
    *,
    intrinsic_width: int | None = None,
    intrinsic_height: int | None = None,
    alpha_threshold: float = _DEFAULT_ALPHA_THRESHOLD,
) -> tuple[float, float] | None:
    """Canvas-normalized centroid of occupied support mask projected through support quad."""

    sup_bounds = normalized_bounds(support)
    if sup_bounds.width <= 0.0 or sup_bounds.height <= 0.0:
        return None

    sum_x = 0.0
    sum_y = 0.0
    weight = 0.0
    step = max(4, min(mask.width, mask.height) // 16)
    for row in range(0, mask.height, step):
        for col in range(0, mask.width, step):
            u = (col + 0.5) / mask.width
            v = (row + 0.5) / mask.height
            if mask.sample(u, v) < alpha_threshold:
                continue
            cx, cy = _mask_uv_to_canvas(
                u,
                v,
                sup_bounds.left,
                sup_bounds.top,
                sup_bounds.right,
                sup_bounds.bottom,
                intrinsic_width=intrinsic_width or support.source_width,
                intrinsic_height=intrinsic_height or support.source_height,
            )
            value = mask.sample(u, v)
            sum_x += cx * value
            sum_y += cy * value
            weight += value
    if weight <= 0.0:
        return None
    return (
        min(1.0, max(0.0, sum_x / weight)),
        min(1.0, max(0.0, sum_y / weight)),
    )


def decode_support_surface_mask(data: bytes) -> SupportSurfaceMask:
    """Decode a grayscale or RGBA PNG/JPEG mask into normalized luminance samples."""

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("Pillow is required to decode support surface masks") from exc

    with Image.open(BytesIO(data)) as image:
        gray = image.convert("L")
        width, height = gray.size
        pixels = list(gray.getdata())
    samples = tuple(value / 255.0 for value in pixels)
    return SupportSurfaceMask(width=width, height=height, samples=samples)


def _point_in_bounds(
    x: float,
    y: float,
    left: float,
    top: float,
    right: float,
    bottom: float,
) -> bool:
    return left <= x <= right and top <= y <= bottom


def _canvas_to_mask_uv(
    cx: float,
    cy: float,
    left: float,
    top: float,
    right: float,
    bottom: float,
    *,
    intrinsic_width: int | None,
    intrinsic_height: int | None,
) -> tuple[float, float]:
    quad_w = right - left
    quad_h = bottom - top
    if quad_w <= 0.0 or quad_h <= 0.0:
        return 0.0, 0.0
    u_quad = (cx - left) / quad_w
    v_quad = (cy - top) / quad_h
    if intrinsic_width is None or intrinsic_height is None or intrinsic_width <= 0 or intrinsic_height <= 0:
        return u_quad, v_quad
    return _letterbox_uv(u_quad, v_quad, quad_w / quad_h, intrinsic_width / intrinsic_height)


def _mask_uv_to_canvas(
    u: float,
    v: float,
    left: float,
    top: float,
    right: float,
    bottom: float,
    *,
    intrinsic_width: int | None,
    intrinsic_height: int | None,
) -> tuple[float, float]:
    quad_w = right - left
    quad_h = bottom - top
    if intrinsic_width is None or intrinsic_height is None or intrinsic_width <= 0 or intrinsic_height <= 0:
        return left + u * quad_w, top + v * quad_h
    u_quad, v_quad = _unletterbox_uv(u, v, quad_w / quad_h, intrinsic_width / intrinsic_height)
    return left + u_quad * quad_w, top + v_quad * quad_h


def _letterbox_uv(
    u_quad: float,
    v_quad: float,
    quad_aspect: float,
    image_aspect: float,
) -> tuple[float, float]:
    if image_aspect <= 0.0 or quad_aspect <= 0.0:
        return u_quad, v_quad
    if quad_aspect > image_aspect:
        scale = image_aspect / quad_aspect
        offset = (1.0 - scale) / 2.0
        return min(1.0, max(0.0, (u_quad - offset) / scale)), v_quad
    scale = quad_aspect / image_aspect
    offset = (1.0 - scale) / 2.0
    return u_quad, min(1.0, max(0.0, (v_quad - offset) / scale))


def _unletterbox_uv(
    u: float,
    v: float,
    quad_aspect: float,
    image_aspect: float,
) -> tuple[float, float]:
    if image_aspect <= 0.0 or quad_aspect <= 0.0:
        return u, v
    if quad_aspect > image_aspect:
        scale = image_aspect / quad_aspect
        offset = (1.0 - scale) / 2.0
        return offset + u * scale, v
    scale = quad_aspect / image_aspect
    offset = (1.0 - scale) / 2.0
    return u, offset + v * scale


def check_on_surface_support_region(
    dependent: SupportOverlapObject,
    support: SupportOverlapObject | SupportOverlapTimelineObject,
    artifacts: PlacementOverlapArtifacts | None,
    *,
    required_overlap_ratio: float,
    alpha_threshold: float = _DEFAULT_ALPHA_THRESHOLD,
) -> OnSurfaceSupportRegionResult:
    """Alias for :func:`evaluate_on_surface_support_region`."""

    return evaluate_on_surface_support_region(
        dependent,
        support,
        artifacts,
        required_overlap_ratio=required_overlap_ratio,
        alpha_threshold=alpha_threshold,
    )


__all__ = [
    "OnSurfaceSupportRegionResult",
    "OverlapValidationContext",
    "PlacementOverlapArtifacts",
    "SupportSurfaceMask",
    "check_on_surface_support_region",
    "evaluate_on_surface_support_region",
    "overlap_artifacts_for_support",
    "decode_support_surface_mask",
    "resolve_support_overlap_ratio",
    "support_mask_centroid_canvas",
    "support_overlap_ratio_bbox",
    "support_overlap_ratio_mask",
]
