"""Org-scoped CRUD routes for pages."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models.audit_log import AuditLog
from content_lab_api.models.org import Org
from content_lab_api.models.page import Page, PageKind
from content_lab_api.schemas.pages import (
    PageCreate,
    PageOut,
    PageUpdate,
    dump_page_metadata,
    page_to_out,
)
from content_lab_shared.logging import ANONYMOUS_ACTOR

router = APIRouter(prefix="/orgs/{org_id}/pages", tags=["pages"])


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


def _record_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    action: str,
    page: Page,
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
            resource_type="page",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(page.id),
            payload=payload,
        )
    )


def _raise_duplicate_page_error(exc: IntegrityError) -> None:
    message = str(exc.orig if exc.orig is not None else exc)
    if "uq_pages_org_platform_external_page_id" in message:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A page with this platform and external_page_id already exists for the org",
        ) from exc
    raise exc


@router.post("", response_model=PageOut, status_code=status.HTTP_201_CREATED)
def create_page(
    org_id: uuid.UUID,
    body: PageCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> PageOut:
    _get_org_or_404(db, org_id)
    page = Page(
        org_id=org_id,
        platform=body.platform,
        display_name=body.display_name,
        external_page_id=body.external_page_id,
        handle=body.handle,
        kind=body.ownership.value,
        metadata_=dump_page_metadata(body.metadata),
    )
    db.add(page)
    try:
        db.flush()
        _record_audit(
            db,
            request,
            org_id=org_id,
            action="page.created",
            page=page,
            payload={
                "ownership": page.kind,
                "platform": page.platform,
                "display_name": page.display_name,
                "external_page_id": page.external_page_id,
                "handle": page.handle,
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_duplicate_page_error(exc)
    db.refresh(page)
    return page_to_out(page)


@router.get("", response_model=list[PageOut])
def list_pages(
    org_id: uuid.UUID,
    ownership: PageKind | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[PageOut]:
    _get_org_or_404(db, org_id)
    query = db.query(Page).filter(Page.org_id == org_id)
    if ownership is not None:
        query = query.filter(Page.kind == ownership.value)
    pages = query.order_by(Page.created_at.desc(), Page.id.desc()).all()
    return [page_to_out(page) for page in pages]


@router.get("/{page_id}", response_model=PageOut)
def get_page(org_id: uuid.UUID, page_id: uuid.UUID, db: Session = Depends(get_db)) -> PageOut:
    page = _get_page_or_404(db, org_id, page_id)
    return page_to_out(page)


@router.patch("/{page_id}", response_model=PageOut)
def update_page(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    body: PageUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> PageOut:
    page = _get_page_or_404(db, org_id, page_id)
    changes = body.model_dump(exclude_unset=True)

    if "display_name" in changes:
        page.display_name = body.display_name
    if "external_page_id" in changes:
        page.external_page_id = body.external_page_id
    if "handle" in changes:
        page.handle = body.handle
    if "ownership" in changes and body.ownership is not None:
        page.kind = body.ownership.value
    if "metadata" in changes and body.metadata is not None:
        page.metadata_ = dump_page_metadata(body.metadata)

    try:
        db.flush()
        _record_audit(
            db,
            request,
            org_id=org_id,
            action="page.updated",
            page=page,
            payload={
                "updated_fields": sorted(changes),
                "ownership": page.kind,
                "platform": page.platform,
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_duplicate_page_error(exc)
    db.refresh(page)
    return page_to_out(page)
