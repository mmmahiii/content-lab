"""Org-scoped get/update routes for policy state."""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import insert
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models.audit_log import AuditLog
from content_lab_api.models.org import Org
from content_lab_api.models.page import Page
from content_lab_api.models.policy_state import PolicyState
from content_lab_api.schemas.policy import (
    PolicyScopeType,
    PolicyStateDocument,
    PolicyStateOut,
    PolicyStateUpdate,
    dump_policy_state,
    parse_policy_state,
)
from content_lab_shared.logging import ANONYMOUS_ACTOR

router = APIRouter(prefix="/orgs/{org_id}/policy", tags=["policy"])

_NICHE_SCOPE_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


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


def _normalize_niche_scope_id(raw_scope_id: str) -> str:
    normalized = "-".join(raw_scope_id.strip().lower().split())
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Niche scope must not be blank",
        )
    if len(normalized) > 120:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Niche scope must be at most 120 characters",
        )
    if _NICHE_SCOPE_PATTERN.fullmatch(normalized) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Niche scope must use lowercase letters, numbers, hyphens, or underscores",
        )
    return normalized


def _policy_key(scope_type: PolicyScopeType, *, scope_id: str | None = None) -> str:
    if scope_type is PolicyScopeType.GLOBAL:
        return PolicyScopeType.GLOBAL.value
    assert scope_id is not None
    return f"{scope_type.value}:{scope_id}"


def _load_policy_document(policy: PolicyState) -> PolicyStateDocument:
    try:
        return parse_policy_state(policy.state)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored policy state is invalid",
        ) from exc


def _get_policy_or_404(db: Session, org_id: uuid.UUID, *, policy_key: str) -> PolicyState:
    policy = (
        db.query(PolicyState)
        .filter(PolicyState.org_id == org_id, PolicyState.policy_key == policy_key)
        .one_or_none()
    )
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


def _serialize_policy(
    policy: PolicyState,
    *,
    scope_type: PolicyScopeType,
    scope_id: str | None,
) -> PolicyStateOut:
    return PolicyStateOut(
        id=policy.id,
        org_id=policy.org_id,
        scope_type=scope_type,
        scope_id=scope_id,
        state=_load_policy_document(policy),
        updated_at=policy.updated_at,
    )


def _record_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    action: str,
    policy: PolicyState,
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
            resource_type="policy_state",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(policy.id),
            payload=payload,
        )
    )


def _upsert_policy(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    scope_type: PolicyScopeType,
    scope_id: str | None,
    body: PolicyStateUpdate,
) -> PolicyStateOut:
    policy_key = _policy_key(scope_type, scope_id=scope_id)
    policy = (
        db.query(PolicyState)
        .filter(PolicyState.org_id == org_id, PolicyState.policy_key == policy_key)
        .one_or_none()
    )

    previous_state = _load_policy_document(policy) if policy is not None else None
    merged_payload = (
        previous_state.model_dump(mode="json")
        if previous_state is not None
        else PolicyStateDocument().model_dump(mode="json")
    )
    changes = body.model_dump(exclude_unset=True, exclude_none=True, mode="json")
    merged_payload.update(changes)
    next_state = PolicyStateDocument.model_validate(merged_payload)

    if policy is None:
        created = True
        policy = PolicyState(
            org_id=org_id, policy_key=policy_key, state=dump_policy_state(next_state)
        )
        policy.org = _get_org_or_404(db, org_id)
        db.add(policy)
    else:
        created = False
        policy.state = dump_policy_state(next_state)

    db.flush()
    _record_audit(
        db,
        request,
        org_id=org_id,
        action="policy.created" if created else "policy.updated",
        policy=policy,
        payload={
            "scope_type": scope_type.value,
            "scope_id": scope_id,
            "policy_key": policy_key,
            "updated_fields": sorted(changes),
            "before": None if previous_state is None else previous_state.model_dump(mode="json"),
            "after": next_state.model_dump(mode="json"),
        },
    )
    db.commit()
    db.refresh(policy)
    return _serialize_policy(policy, scope_type=scope_type, scope_id=scope_id)


@router.get("/global", response_model=PolicyStateOut)
def get_global_policy(org_id: uuid.UUID, db: Session = Depends(get_db)) -> PolicyStateOut:
    _get_org_or_404(db, org_id)
    policy = _get_policy_or_404(db, org_id, policy_key=_policy_key(PolicyScopeType.GLOBAL))
    return _serialize_policy(policy, scope_type=PolicyScopeType.GLOBAL, scope_id=None)


@router.patch("/global", response_model=PolicyStateOut)
def update_global_policy(
    org_id: uuid.UUID,
    body: PolicyStateUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> PolicyStateOut:
    _get_org_or_404(db, org_id)
    return _upsert_policy(
        db,
        request,
        org_id=org_id,
        scope_type=PolicyScopeType.GLOBAL,
        scope_id=None,
        body=body,
    )


@router.get("/page/{page_id}", response_model=PolicyStateOut)
def get_page_policy(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> PolicyStateOut:
    page = _get_page_or_404(db, org_id, page_id)
    policy = _get_policy_or_404(
        db,
        org_id,
        policy_key=_policy_key(PolicyScopeType.PAGE, scope_id=str(page.id)),
    )
    return _serialize_policy(policy, scope_type=PolicyScopeType.PAGE, scope_id=str(page.id))


@router.patch("/page/{page_id}", response_model=PolicyStateOut)
def update_page_policy(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    body: PolicyStateUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> PolicyStateOut:
    page = _get_page_or_404(db, org_id, page_id)
    return _upsert_policy(
        db,
        request,
        org_id=org_id,
        scope_type=PolicyScopeType.PAGE,
        scope_id=str(page.id),
        body=body,
    )


@router.get("/niche/{niche_key}", response_model=PolicyStateOut)
def get_niche_policy(
    org_id: uuid.UUID,
    niche_key: str,
    db: Session = Depends(get_db),
) -> PolicyStateOut:
    _get_org_or_404(db, org_id)
    scope_id = _normalize_niche_scope_id(niche_key)
    policy = _get_policy_or_404(
        db,
        org_id,
        policy_key=_policy_key(PolicyScopeType.NICHE, scope_id=scope_id),
    )
    return _serialize_policy(policy, scope_type=PolicyScopeType.NICHE, scope_id=scope_id)


@router.patch("/niche/{niche_key}", response_model=PolicyStateOut)
def update_niche_policy(
    org_id: uuid.UUID,
    niche_key: str,
    body: PolicyStateUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> PolicyStateOut:
    _get_org_or_404(db, org_id)
    scope_id = _normalize_niche_scope_id(niche_key)
    return _upsert_policy(
        db,
        request,
        org_id=org_id,
        scope_type=PolicyScopeType.NICHE,
        scope_id=scope_id,
        body=body,
    )
