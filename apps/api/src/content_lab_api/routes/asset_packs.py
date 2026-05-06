"""Org-scoped asset pack planning endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models import Asset, AssetGenParam
from content_lab_api.routes._storage import build_signed_download
from content_lab_api.schemas.asset import AssetDetailOut
from content_lab_api.schemas.asset_packs import (
    ApprovedAssetPackGenerateRequest,
    AssetLedIdeasOut,
    AssetLedIdeasRequest,
    AssetPackBatchOut,
    AssetPackBatchRequest,
    AssetPackItemOut,
    AssetPackOut,
    AssetPackPlanOut,
    AssetPackPlanRequest,
    AssetPackRegeneratePlanRequest,
    AssetPackReviewDecisionRequest,
    SourceAssetRegisterOut,
    SourceAssetRegisterRequest,
)
from content_lab_api.services import (
    approve_asset_pack_plan,
    build_asset_led_reel_ideas,
    create_asset_pack_batch,
    create_asset_pack_plan,
    generate_approved_asset_pack,
    regenerate_asset_pack_plan,
    register_source_asset_for_pack,
    reject_asset_pack_plan,
)

router = APIRouter(prefix="/orgs/{org_id}/asset-packs", tags=["asset-packs"])


@router.post("/plan", response_model=AssetPackPlanOut, status_code=status.HTTP_201_CREATED)
def plan_asset_pack(
    org_id: uuid.UUID,
    body: AssetPackPlanRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackPlanOut:
    return create_asset_pack_plan(db, request, org_id=org_id, body=body)


@router.post("/generate", response_model=AssetPackBatchOut, status_code=status.HTTP_201_CREATED)
def generate_asset_pack(
    org_id: uuid.UUID,
    body: AssetPackBatchRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackBatchOut:
    return create_asset_pack_batch(db, request, org_id=org_id, body=body)


@router.post("/{asset_pack_id}/approve", response_model=AssetPackOut)
def approve_asset_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackReviewDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackOut:
    return approve_asset_pack_plan(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )


@router.post("/{asset_pack_id}/reject", response_model=AssetPackOut)
def reject_asset_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackReviewDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackOut:
    return reject_asset_pack_plan(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )


@router.post("/{asset_pack_id}/regenerate-plan", response_model=AssetPackPlanOut)
def regenerate_asset_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackRegeneratePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackPlanOut:
    return regenerate_asset_pack_plan(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )


@router.post(
    "/{asset_pack_id}/generate",
    response_model=AssetPackBatchOut,
    status_code=status.HTTP_201_CREATED,
)
def generate_approved_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: ApprovedAssetPackGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackBatchOut:
    return generate_approved_asset_pack(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )


@router.post("/{asset_pack_id}/ideas", response_model=AssetLedIdeasOut)
def generate_asset_led_ideas(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetLedIdeasRequest,
    db: Session = Depends(get_db),
) -> AssetLedIdeasOut:
    return build_asset_led_reel_ideas(
        db,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        target_concept_count=body.target_concept_count,
        selected_asset_ids=body.selected_asset_ids,
        format_filters=body.format_filters,
        style_filters=body.style_filters,
        selection_mode=body.selection_mode,
    )


@router.post(
    "/{asset_pack_id}/source-assets",
    response_model=SourceAssetRegisterOut,
    status_code=status.HTTP_201_CREATED,
)
def register_source_asset(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: SourceAssetRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SourceAssetRegisterOut:
    asset, item, reused_existing = register_source_asset_for_pack(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )
    return SourceAssetRegisterOut(
        asset=_asset_detail_out(db, asset=asset),
        item=AssetPackItemOut.model_validate(item),
        reused_existing_asset=reused_existing,
    )


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
