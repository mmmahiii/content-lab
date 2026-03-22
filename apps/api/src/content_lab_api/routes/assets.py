"""Org-scoped asset registry resolution endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models import Asset, AssetGenParam, AuditLog, Org, Task
from content_lab_api.schemas.assets import AssetResolveDecision, AssetResolveRequest
from content_lab_assets.registry import (
    AssetKey,
    GenerateDecision,
    GenerationIntent,
    Phase1ProviderLockError,
    ReuseExactDecision,
    build_asset_key,
)
from content_lab_shared.logging import ANONYMOUS_ACTOR

router = APIRouter(prefix="/orgs/{org_id}/assets", tags=["assets"])

_GENERATION_TASK_TYPE = "asset.generate"


def _get_org_or_404(db: Session, org_id: uuid.UUID) -> Org:
    org = db.get(Org, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    return org


def _actor_info(request: Request) -> tuple[str | None, str]:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    return actor_id, actor_type


def _record_generation_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    task: Task,
    asset_key: AssetKey,
) -> None:
    actor_id, actor_type = _actor_info(request)
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action="asset.generate.requested",
            resource_type="task",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(task.id),
            payload={
                "task_type": task.task_type,
                "task_status": task.status,
                "asset_key_hash": asset_key.asset_key_hash,
                "provider": asset_key.canonical_params["provider"],
                "model": asset_key.canonical_params["model"],
            },
        )
    )


def _task_idempotency_key(asset_key_hash: str) -> str:
    return f"{_GENERATION_TASK_TYPE}:{asset_key_hash}"


def _get_generation_task(db: Session, *, org_id: uuid.UUID, idempotency_key: str) -> Task | None:
    return (
        db.query(Task)
        .filter(Task.org_id == org_id, Task.idempotency_key == idempotency_key)
        .one_or_none()
    )


def _build_generation_task_payload(
    body: AssetResolveRequest, asset_key: AssetKey
) -> dict[str, Any]:
    request_payload = jsonable_encoder(body.model_dump(mode="python"))
    canonical_params = jsonable_encoder(asset_key.canonical_params)
    return {
        "resolution": "generate",
        "request": request_payload,
        "asset_key": asset_key.asset_key,
        "asset_key_hash": asset_key.asset_key_hash,
        "canonical_params": canonical_params,
        "provider_submission": {
            "provider": canonical_params["provider"],
            "model": canonical_params["model"],
            "asset_class": canonical_params["asset_class"],
        },
        "provenance": {
            "source": "asset_registry.resolve",
            "phase": "phase1_exact_reuse",
            "reference_asset_ids": canonical_params.get("reference_asset_ids", []),
            "init_image_hash": canonical_params.get("init_image_hash"),
        },
    }


def _ensure_generation_task(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    body: AssetResolveRequest,
    asset_key: AssetKey,
) -> Task:
    idempotency_key = _task_idempotency_key(asset_key.asset_key_hash)
    existing = _get_generation_task(db, org_id=org_id, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    task_id = uuid.uuid4()
    payload = _build_generation_task_payload(body, asset_key)
    try:
        db.execute(
            insert(Task).values(
                id=task_id,
                org_id=org_id,
                task_type=_GENERATION_TASK_TYPE,
                idempotency_key=idempotency_key,
                status="pending",
                payload=payload,
            )
        )
        task = db.query(Task).filter(Task.id == task_id).one()
        _record_generation_audit(db, request, org_id=org_id, task=task, asset_key=asset_key)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _get_generation_task(db, org_id=org_id, idempotency_key=idempotency_key)
        if existing is None:
            raise
        return existing

    db.refresh(task)
    return task


def _get_exact_reuse_asset(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_key_hash: str,
) -> Asset | None:
    return (
        db.query(Asset)
        .filter(
            Asset.org_id == org_id,
            Asset.asset_key_hash == asset_key_hash,
            Asset.status == "active",
        )
        .order_by(Asset.created_at.desc(), Asset.id.desc())
        .one_or_none()
    )


def _get_matching_gen_params(
    db: Session, *, asset: Asset, asset_key_hash: str
) -> AssetGenParam | None:
    return (
        db.query(AssetGenParam)
        .filter(
            AssetGenParam.asset_id == asset.id,
            AssetGenParam.asset_key_hash == asset_key_hash,
        )
        .order_by(AssetGenParam.seq.desc())
        .one_or_none()
    )


def _reuse_exact_decision(
    asset: Asset, *, asset_key: AssetKey, gen_params: AssetGenParam | None
) -> ReuseExactDecision:
    return ReuseExactDecision(
        asset_id=asset.id,
        asset_class=asset.asset_class,
        storage_uri=asset.storage_uri,
        asset_key=asset_key.asset_key,
        asset_key_hash=asset_key.asset_key_hash,
        provider=asset_key.canonical_params["provider"],
        model=asset_key.canonical_params["model"],
        canonical_params=(
            asset_key.canonical_params
            if gen_params is None
            else jsonable_encoder(gen_params.canonical_params)
        ),
        provenance={
            "source": "asset_registry",
            "resolution": "exact_memoisation",
            "matched_via": "asset_key_hash",
            "asset_gen_param_seq": None if gen_params is None else gen_params.seq,
        },
    )


def _generate_decision(
    task: Task,
    *,
    asset_key: AssetKey,
    payload: dict[str, Any],
) -> GenerateDecision:
    generation_intent = GenerationIntent(
        task_id=task.id,
        task_type=task.task_type,
        task_status=task.status,
        idempotency_key=task.idempotency_key,
        asset_class=asset_key.canonical_params["asset_class"],
        provider=asset_key.canonical_params["provider"],
        model=asset_key.canonical_params["model"],
        asset_key=asset_key.asset_key,
        asset_key_hash=asset_key.asset_key_hash,
        payload=payload,
    )
    return GenerateDecision(
        asset_class=asset_key.canonical_params["asset_class"],
        asset_key=asset_key.asset_key,
        asset_key_hash=asset_key.asset_key_hash,
        provider=asset_key.canonical_params["provider"],
        model=asset_key.canonical_params["model"],
        canonical_params=asset_key.canonical_params,
        generation_intent=generation_intent,
        provenance={
            "source": "asset_registry",
            "resolution": "generate",
            "task_id": str(task.id),
        },
    )


@router.post("/resolve", response_model=AssetResolveDecision)
def resolve_asset(
    org_id: uuid.UUID,
    body: AssetResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetResolveDecision:
    _get_org_or_404(db, org_id)
    try:
        asset_key = build_asset_key(
            asset_class=body.asset_class,
            provider=body.provider,
            model=body.model,
            prompt=body.prompt,
            negative_prompt=body.negative_prompt,
            seed=body.seed,
            duration_seconds=body.duration_seconds,
            fps=body.fps,
            ratio=body.ratio,
            motion=body.motion,
            init_image_hash=body.init_image_hash,
            reference_asset_ids=body.reference_asset_ids,
        )
    except Phase1ProviderLockError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    asset = _get_exact_reuse_asset(db, org_id=org_id, asset_key_hash=asset_key.asset_key_hash)
    if asset is not None:
        gen_params = _get_matching_gen_params(
            db, asset=asset, asset_key_hash=asset_key.asset_key_hash
        )
        return _reuse_exact_decision(asset, asset_key=asset_key, gen_params=gen_params)

    task = _ensure_generation_task(db, request, org_id=org_id, body=body, asset_key=asset_key)
    payload = jsonable_encoder(task.payload)
    return _generate_decision(task, asset_key=asset_key, payload=payload)
