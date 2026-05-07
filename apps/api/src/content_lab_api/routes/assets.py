"""Org-scoped asset registry resolution endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models import (
    Asset,
    AssetGenParam,
    AssetPackItem,
    AssetPerformanceSummary,
    AssetUsageSummary,
    Org,
)
from content_lab_api.routes._storage import build_signed_download
from content_lab_api.schemas.asset import AssetDetailOut, SignedDownloadOut
from content_lab_api.schemas.assets import (
    ApprovedExternalImportOut,
    ApprovedExternalImportRequest,
    AssetLibraryItemOut,
    AssetResolveDecision,
    AssetResolveRequest,
)
from content_lab_api.services import import_approved_external_asset, resolve_asset_request

router = APIRouter(prefix="/orgs/{org_id}/assets", tags=["assets"])


def _get_org_or_404(db: Session, org_id: uuid.UUID) -> Org:
    org = db.get(Org, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    return org


def _get_asset_or_404(db: Session, *, org_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    asset = db.query(Asset).filter(Asset.org_id == org_id, Asset.id == asset_id).one_or_none()
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


def _latest_gen_params(db: Session, *, asset_id: uuid.UUID) -> AssetGenParam | None:
    return (
        db.query(AssetGenParam)
        .filter(AssetGenParam.asset_id == asset_id)
        .order_by(AssetGenParam.seq.desc())
        .one_or_none()
    )


def _asset_detail_out(db: Session, *, asset: Asset) -> AssetDetailOut:
    gen_params = _latest_gen_params(db, asset_id=asset.id)
    provenance: dict[str, Any] = {
        "source": asset.source,
        "storage_uri": asset.storage_uri,
    }
    if asset.asset_key is not None:
        provenance["asset_key"] = asset.asset_key
    if asset.asset_key_hash is not None:
        provenance["asset_key_hash"] = asset.asset_key_hash
    if gen_params is not None:
        provenance["asset_gen_param_seq"] = gen_params.seq

    return AssetDetailOut(
        id=asset.id,
        org_id=asset.org_id,
        asset_class=asset.asset_class,
        status=asset.status,
        source=asset.source,
        storage_uri=asset.storage_uri,
        asset_key=asset.asset_key,
        asset_key_hash=asset.asset_key_hash,
        content_hash=asset.content_hash,
        metadata=asset.metadata_,
        canonical_params=None
        if gen_params is None
        else jsonable_encoder(gen_params.canonical_params),
        provenance=provenance,
        download=build_signed_download(storage_uri=asset.storage_uri),
        created_at=asset.created_at,
    )


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _asset_component_metadata(asset: Asset) -> dict[str, Any]:
    metadata = dict(asset.metadata_ or {})
    intent = _mapping_or_empty(metadata.get("intent"))
    request_payload = _mapping_or_empty(intent.get("request"))
    request_metadata = _mapping_or_empty(request_payload.get("metadata"))
    transparency = _mapping_or_empty(metadata.get("transparency"))

    has_transparency = (
        transparency.get("has_transparency")
        if "has_transparency" in transparency
        else metadata.get("has_transparency") or request_metadata.get("has_transparency")
    )
    return {
        "asset_kind": metadata.get("asset_kind")
        or intent.get("asset_kind")
        or request_payload.get("asset_kind"),
        "media_type": metadata.get("media_type")
        or intent.get("media_type")
        or request_payload.get("media_type"),
        "niche": metadata.get("niche")
        or request_metadata.get("asset_pack_niche")
        or request_metadata.get("niche"),
        "tags": _string_list(metadata.get("tags") or request_metadata.get("tags")),
        "has_transparency": _optional_bool(has_transparency),
    }


def _performance_score(summary: AssetPerformanceSummary | None) -> float | None:
    if summary is None:
        return None
    averages = dict(summary.metric_averages or {})
    for key in ("performance_score", "score", "engagement_score"):
        value = averages.get(key)
        if isinstance(value, int | float):
            return float(value)
    numeric_values = [float(value) for value in averages.values() if isinstance(value, int | float)]
    if not numeric_values:
        return None
    return sum(numeric_values) / len(numeric_values)


def _asset_library_item_out(
    asset: Asset,
    *,
    asset_pack_ids: list[uuid.UUID],
    performance_summary: AssetPerformanceSummary | None,
    usage_summary: AssetUsageSummary | None,
) -> AssetLibraryItemOut:
    component = _asset_component_metadata(asset)
    return AssetLibraryItemOut(
        id=asset.id,
        org_id=asset.org_id,
        asset_class=asset.asset_class,
        asset_kind=None if component["asset_kind"] is None else str(component["asset_kind"]),
        media_type=None if component["media_type"] is None else str(component["media_type"]),
        niche=None if component["niche"] is None else str(component["niche"]),
        tags=component["tags"],
        asset_pack_ids=asset_pack_ids,
        has_transparency=component["has_transparency"],
        ready_status=asset.status,
        performance_score=_performance_score(performance_summary),
        reuse_count=0 if usage_summary is None else usage_summary.reuse_count,
        source=asset.source,
        storage_uri=asset.storage_uri,
        metadata=dict(asset.metadata_ or {}),
        created_at=asset.created_at,
    )


@router.post(
    "/import-approved-external",
    response_model=ApprovedExternalImportOut,
    status_code=status.HTTP_201_CREATED,
)
def import_approved_external(
    org_id: uuid.UUID,
    body: ApprovedExternalImportRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ApprovedExternalImportOut:
    """Import bytes from an operator-approved URL into canonical storage (controlled, not a crawler)."""

    _get_org_or_404(db, org_id)
    asset, _item, reused, warnings, licence_ok = import_approved_external_asset(
        db,
        request,
        org_id=org_id,
        body=body,
    )
    return ApprovedExternalImportOut(
        asset_id=asset.id,
        reused_existing_asset=reused,
        import_warnings=warnings,
        licence_metadata_complete=licence_ok,
        asset_pack_item_id=None if _item is None else _item.id,
    )


@router.get("", response_model=list[AssetLibraryItemOut])
def list_assets(
    org_id: uuid.UUID,
    asset_kind: str | None = Query(default=None),
    media_type: str | None = Query(default=None),
    niche: str | None = Query(default=None),
    tags: list[str] = Query(default_factory=list),
    asset_pack_id: uuid.UUID | None = Query(default=None),
    has_transparency: bool | None = Query(default=None),
    ready_status: str | None = Query(default=None),
    performance_score: float | None = Query(default=None, ge=0),
    reuse_count: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AssetLibraryItemOut]:
    _get_org_or_404(db, org_id)
    query = db.query(Asset).filter(Asset.org_id == org_id)
    if ready_status is not None:
        query = query.filter(Asset.status == ready_status)
    if asset_pack_id is not None:
        pack_asset_ids = [
            item.asset_id
            for item in db.query(AssetPackItem.asset_id)
            .filter(
                AssetPackItem.asset_pack_id == asset_pack_id,
                AssetPackItem.asset_id.isnot(None),
            )
            .all()
        ]
        if not pack_asset_ids:
            return []
        query = query.filter(Asset.id.in_(pack_asset_ids))

    assets = query.order_by(Asset.created_at.desc(), Asset.id.desc()).all()
    asset_ids = [asset.id for asset in assets]
    pack_ids_by_asset: dict[uuid.UUID, list[uuid.UUID]] = {asset_id: [] for asset_id in asset_ids}
    if asset_ids:
        for item in (
            db.query(AssetPackItem)
            .filter(AssetPackItem.asset_id.in_(asset_ids))
            .order_by(AssetPackItem.created_at, AssetPackItem.id)
            .all()
        ):
            if item.asset_id is not None:
                pack_ids_by_asset.setdefault(item.asset_id, []).append(item.asset_pack_id)

    usage_by_asset = {
        row.asset_id: row
        for row in db.query(AssetUsageSummary)
        .filter(AssetUsageSummary.org_id == org_id, AssetUsageSummary.asset_id.in_(asset_ids))
        .all()
    }
    performance_by_asset: dict[uuid.UUID, AssetPerformanceSummary] = {}
    for row in (
        db.query(AssetPerformanceSummary)
        .filter(
            AssetPerformanceSummary.org_id == org_id,
            AssetPerformanceSummary.asset_id.in_(asset_ids),
        )
        .order_by(AssetPerformanceSummary.sample_count.desc())
        .all()
    ):
        performance_by_asset.setdefault(row.asset_id, row)

    wanted_tags = {tag for raw in tags for tag in _string_list(raw)}
    rows: list[AssetLibraryItemOut] = []
    for asset in assets:
        row = _asset_library_item_out(
            asset,
            asset_pack_ids=pack_ids_by_asset.get(asset.id, []),
            performance_summary=performance_by_asset.get(asset.id),
            usage_summary=usage_by_asset.get(asset.id),
        )
        if asset_kind is not None and row.asset_kind != asset_kind:
            continue
        if media_type is not None and row.media_type != media_type:
            continue
        if niche is not None and row.niche != niche:
            continue
        if wanted_tags and not wanted_tags.issubset(set(row.tags)):
            continue
        if has_transparency is not None and row.has_transparency is not has_transparency:
            continue
        if performance_score is not None and (
            row.performance_score is None or row.performance_score < performance_score
        ):
            continue
        if reuse_count is not None and row.reuse_count < reuse_count:
            continue
        rows.append(row)

    return rows[offset : offset + limit]


@router.post("/resolve", response_model=AssetResolveDecision)
def resolve_asset(
    org_id: uuid.UUID,
    body: AssetResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetResolveDecision:
    return resolve_asset_request(db, request, org_id=org_id, body=body)


@router.get("/{asset_id}", response_model=AssetDetailOut)
def get_asset(
    org_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> AssetDetailOut:
    _get_org_or_404(db, org_id)
    asset = _get_asset_or_404(db, org_id=org_id, asset_id=asset_id)
    return _asset_detail_out(db, asset=asset)


@router.get("/{asset_id}/download", response_model=SignedDownloadOut)
def get_asset_download(
    org_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> SignedDownloadOut:
    _get_org_or_404(db, org_id)
    asset = _get_asset_or_404(db, org_id=org_id, asset_id=asset_id)
    return build_signed_download(storage_uri=asset.storage_uri)
