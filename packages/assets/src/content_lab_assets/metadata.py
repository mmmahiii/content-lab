"""Derive planner-facing physical metadata from registry asset facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from content_lab_assets.compatibility import (
    AlphaQuality,
    AssetCompatibilityMetadata,
    AssetResolutionClass,
    LightingDirection,
    LightingQuality,
    SurfacePlane,
    ViewAngle,
)
from content_lab_assets.types import AssetKind


def derive_asset_compatibility_metadata(
    *,
    asset_kind: AssetKind | str,
    transparency: bool | Mapping[str, Any] | None = None,
    width: int | None = None,
    height: int | None = None,
    possible_cinematic_roles: Sequence[str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> AssetCompatibilityMetadata:
    """Create conservative compatibility metadata for any registry asset."""

    kind = AssetKind(asset_kind) if not isinstance(asset_kind, AssetKind) else asset_kind
    roles = {_normalize(role) for role in possible_cinematic_roles or []}
    has_transparency = _has_transparency(transparency)
    resolution_class = resolution_class_for_dimensions(width=width, height=height)
    is_environment = kind in _BASE_KINDS or "environment_base" in roles
    is_atmospheric = bool(roles.intersection({"atmospheric_layer", "motion_layer"}))
    is_cutout = has_transparency or kind in _CUTOUT_KINDS
    can_be_full_frame = is_environment and not has_transparency and resolution_class is not AssetResolutionClass.LOW
    can_support = is_environment and not has_transparency
    can_be_supported = kind in _SUPPORTED_KINDS or bool(
        roles.intersection({"hero_subject", "supporting_subject", "foreground_texture", "narrative_payoff"})
    )
    if is_atmospheric:
        can_be_supported = False

    metadata = AssetCompatibilityMetadata(
        view_angle=_default_view_angle(kind, roles),
        surface_plane=_default_surface_plane(kind, roles, is_environment=is_environment, is_atmospheric=is_atmospheric),
        lighting_direction=LightingDirection.UNKNOWN,
        lighting_quality=LightingQuality.UNKNOWN,
        asset_resolution_class=resolution_class,
        can_be_full_frame_base=can_be_full_frame,
        can_support_objects=can_support,
        can_be_supported_by_surface=can_be_supported,
        natural_support_roles=_natural_support_roles(kind, roles, can_be_supported=can_be_supported),
        alpha_quality=AlphaQuality.CLEAN if is_cutout else AlphaQuality.NONE,
        realism_risk_score=_risk_score(
            resolution_class=resolution_class,
            has_transparency=has_transparency,
            is_environment=is_environment,
            is_atmospheric=is_atmospheric,
        ),
        recommended_min_scale=0.05,
        recommended_max_scale=_recommended_max_scale(resolution_class),
        preferred_screen_regions=_preferred_regions(roles, is_environment=is_environment, is_atmospheric=is_atmospheric),
        forbidden_screen_regions=[] if is_environment else ["full_frame"] if resolution_class is AssetResolutionClass.LOW else [],
        compatible_view_angles=_compatible_view_angles(kind, roles),
        compatible_surface_planes=_compatible_surface_planes(kind, roles),
    )
    if overrides:
        payload = metadata.model_dump(mode="python")
        payload.update(dict(overrides))
        metadata = AssetCompatibilityMetadata.model_validate(payload)
    return metadata


def resolution_class_for_dimensions(
    *,
    width: int | None,
    height: int | None,
) -> AssetResolutionClass:
    """Classify dimensions for vertical reel compositing."""

    if width is None or height is None:
        return AssetResolutionClass.MEDIUM
    shortest = min(width, height)
    longest = max(width, height)
    pixels = width * height
    if shortest < 720 or pixels < 900_000:
        return AssetResolutionClass.LOW
    if shortest >= 1080 and longest >= 1600 and pixels >= 1_900_000:
        return AssetResolutionClass.HIGH
    return AssetResolutionClass.MEDIUM


def _default_view_angle(kind: AssetKind, roles: set[str]) -> ViewAngle:
    if "environment_base" in roles:
        return ViewAngle.THREE_QUARTER
    if kind in {AssetKind.BACKGROUND_IMAGE, AssetKind.BACKGROUND_VIDEO}:
        return ViewAngle.THREE_QUARTER
    if roles.intersection({"foreground_texture", "atmospheric_layer", "motion_layer"}):
        return ViewAngle.FRONT
    return ViewAngle.UNKNOWN


def _default_surface_plane(
    kind: AssetKind,
    roles: set[str],
    *,
    is_environment: bool,
    is_atmospheric: bool,
) -> SurfacePlane:
    if is_atmospheric:
        return SurfacePlane.FLOATING
    if "foreground_texture" in roles:
        return SurfacePlane.VERTICAL
    if is_environment or kind in _BASE_KINDS:
        return SurfacePlane.HORIZONTAL
    return SurfacePlane.UNKNOWN


def _natural_support_roles(
    kind: AssetKind,
    roles: set[str],
    *,
    can_be_supported: bool,
) -> list[str]:
    if not can_be_supported:
        return []
    if kind in {AssetKind.SUBJECT_IMAGE, AssetKind.SUBJECT_VIDEO} or "hero_subject" in roles:
        return ["surface_base", "environment_base"]
    return ["surface_base"]


def _risk_score(
    *,
    resolution_class: AssetResolutionClass,
    has_transparency: bool,
    is_environment: bool,
    is_atmospheric: bool,
) -> float:
    risk = 0.25
    if resolution_class is AssetResolutionClass.LOW:
        risk += 0.25
    if has_transparency and not is_atmospheric:
        risk += 0.12
    if not is_environment:
        risk += 0.08
    return round(min(1.0, risk), 4)


def _recommended_max_scale(resolution_class: AssetResolutionClass) -> float:
    if resolution_class is AssetResolutionClass.LOW:
        return 0.65
    if resolution_class is AssetResolutionClass.MEDIUM:
        return 1.0
    return 1.25


def _preferred_regions(
    roles: set[str],
    *,
    is_environment: bool,
    is_atmospheric: bool,
) -> list[str]:
    if is_environment:
        return ["full_frame", "background"]
    if is_atmospheric:
        return ["full_frame_overlay", "upper_third", "midground"]
    if "background_reveal" in roles:
        return ["upper_left", "upper_right", "background_left", "background_right", "rear", "side"]
    if "hero_subject" in roles:
        return ["center", "lower_middle"]
    return ["foreground", "lower_third", "side"]


def _compatible_view_angles(kind: AssetKind, roles: set[str]) -> list[str]:
    if kind in _BASE_KINDS or "environment_base" in roles:
        return ["top_down", "overhead", "three_quarter", "front"]
    if roles.intersection({"hero_subject", "supporting_subject"}):
        return ["front", "side", "three_quarter", "top_down", "overhead"]
    return []


def _compatible_surface_planes(kind: AssetKind, roles: set[str]) -> list[str]:
    if kind in _BASE_KINDS or "environment_base" in roles:
        return ["horizontal", "angled"]
    if roles.intersection({"hero_subject", "supporting_subject"}):
        return ["horizontal", "angled"]
    return []


def _has_transparency(transparency: bool | Mapping[str, Any] | None) -> bool:
    if isinstance(transparency, bool):
        return transparency
    if isinstance(transparency, Mapping):
        return bool(transparency.get("has_transparency"))
    return False


def _normalize(value: str) -> str:
    return "_".join(str(value).strip().lower().replace("-", "_").split())


_BASE_KINDS = frozenset(
    {
        AssetKind.BACKGROUND_IMAGE,
        AssetKind.BACKGROUND_VIDEO,
        AssetKind.SOURCE_CLIP,
        AssetKind.GENERATED_CLIP,
    }
)
_CUTOUT_KINDS = frozenset(
    {
        AssetKind.TRANSPARENT_CUTOUT_PNG,
        AssetKind.MASKED_IMAGE,
        AssetKind.FOREGROUND_LAYER_IMAGE,
        AssetKind.FOREGROUND_LAYER_VIDEO,
    }
)
_SUPPORTED_KINDS = frozenset(
    {
        AssetKind.OBJECT_IMAGE,
        AssetKind.OBJECT_VIDEO,
        AssetKind.PROP_IMAGE,
        AssetKind.PROP_VIDEO,
        AssetKind.SUBJECT_IMAGE,
        AssetKind.SUBJECT_VIDEO,
        AssetKind.TRANSPARENT_CUTOUT_PNG,
        AssetKind.MASKED_IMAGE,
    }
)


__all__ = ["derive_asset_compatibility_metadata", "resolution_class_for_dimensions"]
