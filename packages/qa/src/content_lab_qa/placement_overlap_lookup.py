"""Build overlap validation context from registry metadata and mask blobs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from content_lab_assets.types import AssetPlacementOverlapMetadata, AssetVisualMetadata
from content_lab_creative.planning_schema import CinematicReelPlan
from content_lab_editing.support_surface_overlap import (
    OverlapValidationContext,
    PlacementOverlapArtifacts,
    SupportSurfaceMask,
    decode_support_surface_mask,
)

FetchMaskBytes = Callable[[str], bytes | None]


def build_overlap_validation_context(
    *,
    assets_by_id: Mapping[str, Mapping[str, Any]],
    mask_uris: set[str],
    fetch_bytes: FetchMaskBytes,
) -> OverlapValidationContext:
    """Resolve support-surface masks for QA and renderer overlap checks."""

    by_asset_id: dict[str, PlacementOverlapArtifacts] = {}
    by_mask_uri: dict[str, PlacementOverlapArtifacts] = {}

    for asset_id, metadata in assets_by_id.items():
        placement = AssetPlacementOverlapMetadata.from_metadata(dict(metadata))
        uri = placement.support_surface_mask_uri
        if not uri:
            continue
        artifacts = _artifacts_for_uri(uri, metadata, fetch_bytes)
        if artifacts is not None:
            by_asset_id[str(asset_id)] = artifacts
            by_mask_uri[uri] = artifacts

    for uri in mask_uris:
        if uri in by_mask_uri:
            continue
        artifacts = _artifacts_for_uri(uri, {}, fetch_bytes)
        if artifacts is not None:
            by_mask_uri[uri] = artifacts

    return OverlapValidationContext(by_asset_id=by_asset_id, by_mask_uri=by_mask_uri)


def collect_mask_uris_from_plan(plan: CinematicReelPlan) -> set[str]:
    uris: set[str] = set()
    for scene in plan.scenes:
        for item in scene.objects:
            if item.support_surface_mask_uri:
                uris.add(item.support_surface_mask_uri)
    return uris


def _artifacts_for_uri(
    uri: str,
    metadata: Mapping[str, Any],
    fetch_bytes: FetchMaskBytes,
) -> PlacementOverlapArtifacts | None:
    data = fetch_bytes(uri)
    if not data:
        return None
    try:
        mask: SupportSurfaceMask = decode_support_surface_mask(data)
    except (OSError, RuntimeError, ValueError):
        return None
    visual = _visual_from_metadata(metadata)
    return PlacementOverlapArtifacts(
        support_surface_mask=mask,
        intrinsic_width=visual.width if visual else None,
        intrinsic_height=visual.height if visual else None,
    )


def _visual_from_metadata(metadata: Mapping[str, Any]) -> AssetVisualMetadata | None:
    raw = metadata.get("visual")
    if isinstance(raw, AssetVisualMetadata):
        return raw
    if isinstance(raw, dict):
        try:
            return AssetVisualMetadata.model_validate(raw)
        except ValueError:
            return None
    width = metadata.get("width")
    height = metadata.get("height")
    if width is not None and height is not None:
        try:
            return AssetVisualMetadata(width=int(width), height=int(height))
        except (TypeError, ValueError):
            return None
    return None


__all__ = [
    "FetchMaskBytes",
    "build_overlap_validation_context",
    "collect_mask_uris_from_plan",
]
