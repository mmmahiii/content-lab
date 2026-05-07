"""Org-scoped asset pack planning endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models import (
    Asset,
    AssetGenParam,
    AssetPack,
    AssetPackItem,
    AuditLog,
    GeneratedReelStatus,
    Org,
    OutboxEvent,
    Page,
    Reel,
    ReelFamily,
    ReelOrigin,
    Run,
    Task,
)
from content_lab_api.routes._storage import build_signed_download
from content_lab_api.schemas.asset import AssetDetailOut
from content_lab_api.schemas.asset_packs import (
    ApprovedAssetPackGenerateRequest,
    AssetLedIdeasOut,
    AssetLedIdeasRequest,
    AssetPackBatchOut,
    AssetPackBatchRequest,
    AssetPackCombinationsOut,
    AssetPackCombinationsRequest,
    AssetPackCompositionSubmitOut,
    AssetPackCompositionSubmitRequest,
    AssetPackCreate,
    AssetPackItemOut,
    AssetPackOut,
    AssetPackPlanOut,
    AssetPackPlanRequest,
    AssetPackRegeneratePlanRequest,
    AssetPackReviewDecisionRequest,
    CandidateCompositionAssetOut,
    CandidateCompositionOut,
    SourceAssetRegisterOut,
    SourceAssetRegisterRequest,
)
from content_lab_api.schemas.runs import FlowTrigger, WorkflowKey
from content_lab_api.services import (
    approve_asset_pack_plan,
    build_asset_led_reel_ideas,
    build_asset_pack_compositions,
    create_asset_pack,
    create_asset_pack_batch,
    create_asset_pack_plan,
    generate_approved_asset_pack,
    plan_existing_asset_pack,
    regenerate_asset_pack_plan,
    register_source_asset_for_pack,
    reject_asset_pack_plan,
)
from content_lab_assets.combinator import CandidateComposition, PackAsset
from content_lab_runs import RunStatus, TaskStatus
from content_lab_shared.logging import ANONYMOUS_ACTOR

router = APIRouter(prefix="/orgs/{org_id}/asset-packs", tags=["asset-packs"])


def _get_org_or_404(db: Session, org_id: uuid.UUID) -> Org:
    org = db.get(Org, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    return org


def _get_asset_pack_or_404(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
) -> AssetPack:
    asset_pack = (
        db.query(AssetPack)
        .filter(AssetPack.org_id == org_id, AssetPack.id == asset_pack_id)
        .one_or_none()
    )
    if asset_pack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset pack not found")
    return asset_pack


def _get_page_or_404(db: Session, *, org_id: uuid.UUID, page_id: uuid.UUID) -> Page:
    page = db.query(Page).filter(Page.org_id == org_id, Page.id == page_id).one_or_none()
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return page


def _actor_info(request: Request) -> tuple[str | None, str]:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    return actor_id, actor_type


def _record_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict[str, Any],
) -> None:
    actor_id, actor_type = _actor_info(request)
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action=action,
            resource_type=resource_type,
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=resource_id,
            payload=payload,
        )
    )


def _candidate_asset_out(asset: PackAsset) -> CandidateCompositionAssetOut:
    return CandidateCompositionAssetOut(
        asset_id=uuid.UUID(asset.asset_id),
        asset_kind=asset.asset_kind.value,
        pack_role=asset.pack_role,
        title=asset.title,
        compatibility=asset.compatibility.model_dump(mode="json"),
        metadata=asset.metadata,
        performance_score=asset.performance_score,
        usage_count=asset.usage_count,
    )


def _composition_manifest(
    *,
    asset_pack: AssetPack,
    candidate: CandidateComposition,
) -> dict[str, Any]:
    roles = {
        role: {
            "asset_id": asset.asset_id,
            "asset_kind": asset.asset_kind.value,
            "pack_role": asset.pack_role,
            "title": asset.title,
            "metadata": asset.metadata,
            "compatibility": asset.compatibility.model_dump(mode="json"),
        }
        for role, asset in sorted(candidate.roles.items())
    }
    return {
        "schema_version": "asset_composition_manifest.v1",
        "asset_pack_id": str(asset_pack.id),
        "composition_id": candidate.composition_id,
        "roles": roles,
        "scores": {
            "compatibility": candidate.compatibility_score,
            "diversity": candidate.diversity_score,
            "performance": candidate.performance_score,
            "selection": candidate.selection_score,
        },
        "reasons": candidate.reasons,
    }


def _candidate_out(
    *,
    asset_pack: AssetPack,
    candidate: CandidateComposition,
) -> CandidateCompositionOut:
    return CandidateCompositionOut(
        composition_id=candidate.composition_id,
        roles={role: _candidate_asset_out(asset) for role, asset in candidate.roles.items()},
        compatibility_score=candidate.compatibility_score,
        diversity_score=candidate.diversity_score,
        performance_score=candidate.performance_score,
        selection_score=candidate.selection_score,
        reasons=candidate.reasons,
        composition_manifest=_composition_manifest(asset_pack=asset_pack, candidate=candidate),
    )


def _composition_title(body: AssetPackCompositionSubmitRequest, asset_pack: AssetPack) -> str:
    raw_title = body.composition_manifest.get("title") or body.composition_manifest.get(
        "composition_id"
    )
    if raw_title:
        return f"{asset_pack.name}: {raw_title}"
    return f"{asset_pack.name} composition preview"


@router.post("", response_model=AssetPackOut, status_code=status.HTTP_201_CREATED)
def create_asset_pack_route(
    org_id: uuid.UUID,
    body: AssetPackCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackOut:
    return create_asset_pack(db, request, org_id=org_id, body=body)


@router.get("", response_model=list[AssetPackOut])
def list_asset_packs(
    org_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    niche: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AssetPackOut]:
    _get_org_or_404(db, org_id)
    query = db.query(AssetPack).filter(AssetPack.org_id == org_id)
    if status_filter is not None:
        query = query.filter(AssetPack.status == status_filter)
    if niche is not None:
        query = query.filter(AssetPack.niche == niche)
    rows = (
        query.order_by(AssetPack.created_at.desc(), AssetPack.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [AssetPackOut.model_validate(row) for row in rows]


@router.post("/plan", response_model=AssetPackPlanOut, status_code=status.HTTP_201_CREATED)
def plan_asset_pack(
    org_id: uuid.UUID,
    body: AssetPackPlanRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackPlanOut:
    return create_asset_pack_plan(db, request, org_id=org_id, body=body)


@router.get("/{asset_pack_id}", response_model=AssetPackOut)
def get_asset_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> AssetPackOut:
    _get_org_or_404(db, org_id)
    return AssetPackOut.model_validate(
        _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    )


@router.post("/{asset_pack_id}/plan", response_model=AssetPackPlanOut)
def plan_existing_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackPlanRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackPlanOut:
    return plan_existing_asset_pack(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )


@router.get("/{asset_pack_id}/items", response_model=list[AssetPackItemOut])
def list_asset_pack_items(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[AssetPackItemOut]:
    _get_org_or_404(db, org_id)
    _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    rows = (
        db.query(AssetPackItem)
        .filter(AssetPackItem.asset_pack_id == asset_pack_id)
        .order_by(AssetPackItem.priority, AssetPackItem.created_at, AssetPackItem.id)
        .all()
    )
    return [AssetPackItemOut.model_validate(row) for row in rows]


@router.post("/{asset_pack_id}/combinations", response_model=AssetPackCombinationsOut)
def generate_asset_pack_combinations(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackCombinationsRequest,
    db: Session = Depends(get_db),
) -> AssetPackCombinationsOut:
    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    try:
        candidates = build_asset_pack_compositions(
            db,
            org_id=org_id,
            asset_pack_id=asset_pack_id,
            target_reel_count=body.target_reel_count,
            format_filters=body.format_filters(),
            style_filters=body.style_filters(),
            selection_mode=body.mode,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return AssetPackCombinationsOut(
        asset_pack=AssetPackOut.model_validate(asset_pack),
        candidate_compositions=[
            _candidate_out(asset_pack=asset_pack, candidate=candidate) for candidate in candidates
        ],
    )


@router.post(
    "/{asset_pack_id}/composition-renders",
    response_model=AssetPackCompositionSubmitOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_asset_pack_composition_render(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackCompositionSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackCompositionSubmitOut:
    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    page = _get_page_or_404(db, org_id=org_id, page_id=body.page_id)
    manifest = dict(body.composition_manifest or {})
    manifest_pack_id = manifest.get("asset_pack_id")
    if manifest_pack_id is not None and str(manifest_pack_id) != str(asset_pack_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="composition_manifest.asset_pack_id must match the route asset_pack_id",
        )
    manifest["asset_pack_id"] = str(asset_pack_id)

    idempotency_key = body.idempotency_key or (
        f"asset-composition-render:{asset_pack_id}:"
        f"{body.render_mode}:{manifest.get('composition_id') or uuid.uuid4()}"
    )
    family = ReelFamily(
        org_id=org_id,
        page_id=page.id,
        name=_composition_title(body, asset_pack),
        metadata_={
            "mode": "asset_composition",
            "asset_pack_id": str(asset_pack_id),
            "render_mode": body.render_mode,
            "composition_manifest": manifest,
            "submission_metadata": dict(body.metadata),
        },
    )
    db.add(family)
    db.flush()
    reel = Reel(
        org_id=org_id,
        reel_family_id=family.id,
        origin=ReelOrigin.GENERATED.value,
        status=GeneratedReelStatus.PLANNING.value,
        variant_label="Preview" if body.render_mode == "preview" else "Final",
        metadata_={
            "asset_pack_id": str(asset_pack_id),
            "composition_manifest": manifest,
            "render_mode": body.render_mode,
            "dry_run": body.dry_run,
        },
    )
    db.add(reel)
    db.flush()
    run = Run(
        org_id=org_id,
        workflow_key=WorkflowKey.PROCESS_REEL.value,
        flow_trigger=FlowTrigger.MANUAL.value,
        status=RunStatus.QUEUED.value,
        idempotency_key=idempotency_key,
        input_params={
            "org_id": str(org_id),
            "page_id": str(page.id),
            "reel_id": str(reel.id),
            "reel_family_id": str(family.id),
            "workflow_stage": "asset_composition_render",
            "asset_pack_id": str(asset_pack_id),
            "composition_manifest": manifest,
            "render_mode": body.render_mode,
            "dry_run": body.dry_run,
        },
        run_metadata={
            "submitted_via": "api",
            "flow_trigger": FlowTrigger.MANUAL.value,
            "client": {
                "workflow_stage": "asset_composition_render",
                "render_mode": body.render_mode,
                **dict(body.metadata),
            },
            "target": {
                "org_id": str(org_id),
                "page_id": str(page.id),
                "asset_pack_id": str(asset_pack_id),
                "reel_id": str(reel.id),
                "reel_family_id": str(family.id),
            },
            "request": {
                "request_id": getattr(request.state, "request_id", None),
                "method": request.method,
                "path": request.url.path,
            },
        },
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A matching composition render run already exists for the org",
        ) from exc

    task = Task(
        org_id=org_id,
        task_type=WorkflowKey.PROCESS_REEL.value,
        idempotency_key=idempotency_key,
        status=TaskStatus.QUEUED.value,
        run_id=run.id,
        payload=dict(run.input_params or {}),
    )
    db.add(task)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A matching composition render task already exists for the org",
        ) from exc
    event = OutboxEvent(
        org_id=org_id,
        aggregate_type="run",
        aggregate_id=str(run.id),
        event_type="orchestration.flow.requested",
        payload={
            "run_id": str(run.id),
            "task_id": str(task.id),
            "org_id": str(org_id),
            "workflow_key": run.workflow_key,
            "flow_trigger": run.flow_trigger,
            "status": run.status,
            "idempotency_key": run.idempotency_key,
            "input_params": dict(run.input_params or {}),
            "run_metadata": dict(run.run_metadata or {}),
            "request_id": getattr(request.state, "request_id", None),
        },
    )
    db.add(event)
    db.flush()
    run.external_ref = f"outbox:{event.id}"
    run_metadata = dict(run.run_metadata or {})
    run_metadata["orchestration"] = {
        "backend": "outbox",
        "event_type": event.event_type,
        "outbox_event_id": str(event.id),
    }
    run.run_metadata = run_metadata
    _record_audit(
        db,
        request,
        org_id=org_id,
        action="asset_pack.composition_render.submitted",
        resource_type="run",
        resource_id=str(run.id),
        payload={
            "asset_pack_id": str(asset_pack_id),
            "page_id": str(page.id),
            "reel_id": str(reel.id),
            "reel_family_id": str(family.id),
            "render_mode": body.render_mode,
            "dry_run": body.dry_run,
        },
    )
    db.commit()
    db.refresh(run)
    db.refresh(task)
    return AssetPackCompositionSubmitOut(
        run_id=run.id,
        task_id=task.id,
        reel_id=reel.id,
        reel_family_id=family.id,
        status=run.status,
        external_ref=run.external_ref,
    )


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
