"""Org-scoped asset registry resolution endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models import Asset, AssetGenParam, Org
from content_lab_api.routes._storage import build_signed_download
from content_lab_api.schemas.asset import AssetDetailOut, SignedDownloadOut
from content_lab_api.schemas.assets import AssetResolveDecision, AssetResolveRequest
from content_lab_api.services import resolve_asset_request

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
