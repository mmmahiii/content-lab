"""Load asset packs and produce compatibility-filtered composition candidates."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from sqlalchemy.orm import Session

from content_lab_api.models import AssetPack, AssetPackItem
from content_lab_assets.combinator import (
    CandidateComposition,
    OutputPotentialEstimate,
    PackAsset,
    estimate_output_potential,
    generate_candidate_compositions,
    select_performance_weighted_combinations,
)


def build_asset_pack_compositions(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    target_reel_count: int,
    format_filters: Sequence[str] | None = None,
    style_filters: Sequence[str] | None = None,
    selection_mode: Literal["balanced", "exploit", "explore", "mutation", "chaos"] = "balanced",
) -> list[CandidateComposition]:
    """Generate candidate compositions from one asset pack."""

    pack_assets = _load_pack_assets(db, org_id=org_id, asset_pack_id=asset_pack_id)
    if selection_mode == "balanced":
        return cast(
            list[CandidateComposition],
            generate_candidate_compositions(
                pack_assets,
                target_reel_count=target_reel_count,
                format_filters=format_filters,
                style_filters=style_filters,
            ),
        )
    return cast(
        list[CandidateComposition],
        select_performance_weighted_combinations(
            pack_assets,
            target_reel_count=target_reel_count,
            format_filters=format_filters,
            style_filters=style_filters,
            mode=selection_mode,
        ),
    )


def estimate_asset_pack_output_potential(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    target_reel_count: int | None = None,
    format_filters: Sequence[str] | None = None,
    style_filters: Sequence[str] | None = None,
) -> OutputPotentialEstimate:
    """Estimate useful reel output for one asset pack."""

    return estimate_output_potential(
        _load_pack_assets(db, org_id=org_id, asset_pack_id=asset_pack_id),
        target_reel_count=target_reel_count,
        format_filters=format_filters,
        style_filters=style_filters,
    )


def _load_pack_assets(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
) -> list[PackAsset]:
    pack = (
        db.query(AssetPack)
        .filter(AssetPack.org_id == org_id, AssetPack.id == asset_pack_id)
        .one_or_none()
    )
    if pack is None:
        raise ValueError(f"Unknown asset_pack_id {asset_pack_id!s}")
    items = (
        db.query(AssetPackItem)
        .filter(AssetPackItem.asset_pack_id == asset_pack_id)
        .order_by(AssetPackItem.priority.asc(), AssetPackItem.created_at.asc())
        .all()
    )
    return [_pack_asset_from_item(item) for item in items if item.asset_id is not None]


def _pack_asset_from_item(item: AssetPackItem) -> PackAsset:
    metadata = _merge_metadata(
        _planned_spec_metadata(item),
        item.metadata_json,
        {"compatibility": item.compatibility_metadata},
    )
    return PackAsset.from_pack_item(
        {
            "id": str(item.id),
            "asset_id": str(item.asset_id),
            "asset_kind": item.asset_kind,
            "pack_role": item.pack_role,
            "metadata": metadata,
            "performance_score": metadata.get("performance_score"),
            "usage_count": metadata.get("usage_count", 0),
        }
    )


def _planned_spec_metadata(item: AssetPackItem) -> dict[str, Any]:
    if item.planned_asset_spec is None:
        return {}
    spec = item.planned_asset_spec
    return {
        "compatible_with": dict(spec.compatible_with or {}),
        "compatibility": dict(spec.compatibility_metadata or {}),
        "format_type": list(spec.intended_reel_formats or []),
    }


def _merge_metadata(*values: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        if value:
            merged.update(dict(value))
    return merged


__all__ = [
    "build_asset_pack_compositions",
    "estimate_asset_pack_output_potential",
]
