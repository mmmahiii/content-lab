"""Org/page-scoped create/list/get routes for reel families."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import insert
from sqlalchemy.orm import Session, selectinload

from content_lab_api.deps import get_db
from content_lab_api.models.audit_log import AuditLog
from content_lab_api.models.org import Org
from content_lab_api.models.page import Page
from content_lab_api.models.reel_family import ReelFamily
from content_lab_api.schemas.reel_families import (
    ReelFamilyCreate,
    ReelFamilyOut,
    dump_reel_family_metadata,
    reel_family_to_out,
)
from content_lab_shared.logging import ANONYMOUS_ACTOR

router = APIRouter(
    prefix="/orgs/{org_id}/pages/{page_id}/reel-families",
    tags=["reel-families"],
)


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
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    family_id: uuid.UUID,
) -> ReelFamily:
    family = (
        db.query(ReelFamily)
        .options(selectinload(ReelFamily.reels))
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


def _record_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    family: ReelFamily,
    action: str,
    payload: dict[str, Any],
) -> None:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action=action,
            resource_type="reel_family",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(family.id),
            payload=payload,
        )
    )


@router.post("", response_model=ReelFamilyOut, status_code=status.HTTP_201_CREATED)
def create_reel_family(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    body: ReelFamilyCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ReelFamilyOut:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)

    family = ReelFamily(
        org_id=org_id,
        page_id=page_id,
        name=body.name,
        metadata_=dump_reel_family_metadata(body.mode, body.metadata),
    )
    db.add(family)

    try:
        db.flush()
        _record_audit(
            db,
            request,
            org_id=org_id,
            family=family,
            action="reel_family.created",
            payload={
                "page_id": str(page_id),
                "name": family.name,
                "mode": body.mode.value,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(family)
    return reel_family_to_out(family)


@router.get("", response_model=list[ReelFamilyOut])
def list_reel_families(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[ReelFamilyOut]:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)

    families = (
        db.query(ReelFamily)
        .options(selectinload(ReelFamily.reels))
        .filter(ReelFamily.org_id == org_id, ReelFamily.page_id == page_id)
        .order_by(ReelFamily.created_at.desc(), ReelFamily.id.desc())
        .all()
    )
    return [reel_family_to_out(family) for family in families]


@router.get("/{family_id}", response_model=ReelFamilyOut)
def get_reel_family(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    family_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ReelFamilyOut:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)
    family = _get_reel_family_or_404(db, org_id, page_id, family_id)
    return reel_family_to_out(family)
