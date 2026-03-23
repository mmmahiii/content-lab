"""Org/page-scoped create/list/get routes for reels and human review actions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import insert
from sqlalchemy.orm import Session, selectinload

from content_lab_api.deps import get_db
from content_lab_api.models.audit_log import AuditLog
from content_lab_api.models.org import Org
from content_lab_api.models.page import Page
from content_lab_api.models.reel import GeneratedReelStatus, Reel, ReelOrigin
from content_lab_api.models.reel_family import ReelFamily
from content_lab_api.schemas.reels import ReelCreate, ReelOut, reel_to_out
from content_lab_shared.logging import ANONYMOUS_ACTOR

router = APIRouter(tags=["reels"])


def _get_org_or_404(db: Session, org_id: uuid.UUID) -> Org:
    org = db.get(Org, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    return org


def _get_page_or_404(db: Session, org_id: uuid.UUID, page_id: uuid.UUID) -> Page:
    page = db.query(Page).filter(Page.org_id == org_id, Page.id == page_id).one_or_none()
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return page


def _get_reel_family_or_404(
    db: Session,
    *,
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    family_id: uuid.UUID,
) -> ReelFamily:
    family = (
        db.query(ReelFamily)
        .filter(
            ReelFamily.org_id == org_id,
            ReelFamily.page_id == page_id,
            ReelFamily.id == family_id,
        )
        .one_or_none()
    )
    if family is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reel family not found")
    return family


def _get_reel_or_404(
    db: Session,
    *,
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    reel_id: uuid.UUID,
) -> Reel:
    reel = (
        db.query(Reel)
        .join(ReelFamily, ReelFamily.id == Reel.reel_family_id)
        .options(selectinload(Reel.reel_family))
        .filter(
            Reel.org_id == org_id,
            Reel.id == reel_id,
            ReelFamily.org_id == org_id,
            ReelFamily.page_id == page_id,
        )
        .one_or_none()
    )
    if reel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reel not found")
    return reel


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
    reel: Reel,
    page_id: uuid.UUID,
    action: str,
    payload: dict[str, Any],
) -> None:
    actor_id, actor_type = _actor_info(request)
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action=action,
            resource_type="reel",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(reel.id),
            payload={
                "page_id": str(page_id),
                "family_id": str(reel.reel_family_id),
                "origin": reel.origin,
                **payload,
            },
        )
    )


def _transition_conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _ensure_generated_reel(reel: Reel) -> None:
    if reel.origin != ReelOrigin.GENERATED.value:
        raise _transition_conflict("Review actions are only allowed for generated reels")


def _approval_payload(actor_id: str | None, *, now: datetime) -> dict[str, Any]:
    payload: dict[str, Any] = {"approved_at": now.isoformat()}
    if actor_id is not None:
        payload["approved_by"] = actor_id
    return payload


def _posting_payload(actor_id: str | None, *, now: datetime) -> dict[str, Any]:
    payload: dict[str, Any] = {"posted_at": now.isoformat()}
    if actor_id is not None:
        payload["posted_by"] = actor_id
    return payload


def _serialize_reel(reel: Reel, *, page_id: uuid.UUID) -> ReelOut:
    return reel_to_out(reel, page_id=page_id)


@router.post(
    "/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels",
    response_model=ReelOut,
    status_code=status.HTTP_201_CREATED,
)
def create_reel(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    family_id: uuid.UUID,
    body: ReelCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ReelOut:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)
    _get_reel_family_or_404(db, org_id=org_id, page_id=page_id, family_id=family_id)

    reel = Reel(
        org_id=org_id,
        reel_family_id=family_id,
        origin=body.origin.value,
        status=body.status.value,
        variant_label=body.variant_label,
        metadata_=dict(body.metadata),
    )
    db.add(reel)

    try:
        db.flush()
        _record_audit(
            db,
            request,
            org_id=org_id,
            reel=reel,
            page_id=page_id,
            action="reel.created",
            payload={
                "status": reel.status,
                "variant_label": reel.variant_label,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(reel)
    return _serialize_reel(reel, page_id=page_id)


def _list_reels(
    db: Session,
    *,
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    family_id: uuid.UUID | None,
    origin: ReelOrigin | None,
    status_value: str | None,
) -> list[Reel]:
    query = (
        db.query(Reel)
        .join(ReelFamily, ReelFamily.id == Reel.reel_family_id)
        .options(selectinload(Reel.reel_family))
        .filter(
            Reel.org_id == org_id,
            ReelFamily.org_id == org_id,
            ReelFamily.page_id == page_id,
        )
    )
    if family_id is not None:
        query = query.filter(Reel.reel_family_id == family_id)
    if origin is not None:
        query = query.filter(Reel.origin == origin.value)
    if status_value is not None:
        query = query.filter(Reel.status == status_value)
    return query.order_by(Reel.created_at.desc(), Reel.id.desc()).all()


@router.get("/orgs/{org_id}/pages/{page_id}/reels", response_model=list[ReelOut])
def list_reels(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    family_id: uuid.UUID | None = Query(default=None),
    origin: ReelOrigin | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[ReelOut]:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)

    reels = _list_reels(
        db,
        org_id=org_id,
        page_id=page_id,
        family_id=family_id,
        origin=origin,
        status_value=status_value,
    )
    return [_serialize_reel(reel, page_id=page_id) for reel in reels]


@router.get(
    "/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels",
    response_model=list[ReelOut],
)
def list_family_reels(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    family_id: uuid.UUID,
    origin: ReelOrigin | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[ReelOut]:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)
    _get_reel_family_or_404(db, org_id=org_id, page_id=page_id, family_id=family_id)

    reels = _list_reels(
        db,
        org_id=org_id,
        page_id=page_id,
        family_id=family_id,
        origin=origin,
        status_value=status_value,
    )
    return [_serialize_reel(reel, page_id=page_id) for reel in reels]


@router.get("/orgs/{org_id}/pages/{page_id}/reels/{reel_id}", response_model=ReelOut)
def get_reel(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    reel_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ReelOut:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)
    reel = _get_reel_or_404(db, org_id=org_id, page_id=page_id, reel_id=reel_id)
    return _serialize_reel(reel, page_id=page_id)


@router.post("/orgs/{org_id}/pages/{page_id}/reels/{reel_id}/approve", response_model=ReelOut)
def approve_reel(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    reel_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> ReelOut:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)
    reel = _get_reel_or_404(db, org_id=org_id, page_id=page_id, reel_id=reel_id)
    _ensure_generated_reel(reel)
    if reel.status != GeneratedReelStatus.READY.value:
        raise _transition_conflict("Only ready generated reels can be approved")
    review = (reel.metadata_ or {}).get("review")
    if isinstance(review, dict) and review.get("approved_at"):
        raise _transition_conflict("Reel has already been approved")

    actor_id, _ = _actor_info(request)
    now = datetime.now(UTC)
    metadata = dict(reel.metadata_ or {})
    metadata["review"] = _approval_payload(actor_id, now=now)
    reel.metadata_ = metadata

    try:
        db.flush()
        _record_audit(
            db,
            request,
            org_id=org_id,
            reel=reel,
            page_id=page_id,
            action="reel.approved",
            payload={
                "prior_status": GeneratedReelStatus.READY.value,
                "new_status": reel.status,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(reel)
    return _serialize_reel(reel, page_id=page_id)


@router.post("/orgs/{org_id}/pages/{page_id}/reels/{reel_id}/archive", response_model=ReelOut)
def archive_reel(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    reel_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> ReelOut:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)
    reel = _get_reel_or_404(db, org_id=org_id, page_id=page_id, reel_id=reel_id)
    _ensure_generated_reel(reel)
    if reel.status != GeneratedReelStatus.READY.value:
        raise _transition_conflict("Only ready generated reels can be archived")

    prior_status = reel.status
    reel.status = GeneratedReelStatus.ARCHIVED.value
    try:
        db.flush()
        _record_audit(
            db,
            request,
            org_id=org_id,
            reel=reel,
            page_id=page_id,
            action="reel.archived",
            payload={
                "prior_status": prior_status,
                "new_status": reel.status,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(reel)
    return _serialize_reel(reel, page_id=page_id)


@router.post("/orgs/{org_id}/pages/{page_id}/reels/{reel_id}/mark-posted", response_model=ReelOut)
def mark_reel_posted(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    reel_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> ReelOut:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)
    reel = _get_reel_or_404(db, org_id=org_id, page_id=page_id, reel_id=reel_id)
    _ensure_generated_reel(reel)
    if reel.status != GeneratedReelStatus.READY.value:
        raise _transition_conflict("Only ready generated reels can be marked posted")

    actor_id, _ = _actor_info(request)
    now = datetime.now(UTC)
    prior_status = reel.status
    metadata = dict(reel.metadata_ or {})
    metadata["posting"] = _posting_payload(actor_id, now=now)
    reel.metadata_ = metadata
    reel.status = GeneratedReelStatus.POSTED.value
    try:
        db.flush()
        _record_audit(
            db,
            request,
            org_id=org_id,
            reel=reel,
            page_id=page_id,
            action="reel.mark_posted",
            payload={
                "prior_status": prior_status,
                "new_status": reel.status,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(reel)
    return _serialize_reel(reel, page_id=page_id)
