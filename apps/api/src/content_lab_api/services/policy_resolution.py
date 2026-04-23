"""Resolve effective page policy without surfacing missing rows as HTTP 404."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from content_lab_api.models.policy_state import PolicyState
from content_lab_api.schemas.policy import (
    PagePolicyStateOut,
    PolicyScopeType,
    PolicyStateDocument,
    parse_policy_state,
)


def policy_key(scope_type: PolicyScopeType, *, scope_id: str | None = None) -> str:
    if scope_type is PolicyScopeType.GLOBAL:
        return PolicyScopeType.GLOBAL.value
    assert scope_id is not None
    return f"{scope_type.value}:{scope_id}"


def fetch_policy_row(
    db: Session, org_id: uuid.UUID, *, policy_key_value: str
) -> PolicyState | None:
    return (
        db.query(PolicyState)
        .filter(PolicyState.org_id == org_id, PolicyState.policy_key == policy_key_value)
        .one_or_none()
    )


def build_page_policy_view(
    *,
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    page_row: PolicyState | None,
    global_row: PolicyState | None,
) -> PagePolicyStateOut:
    """Pure resolution: page row beats global row beats schema defaults."""

    if page_row is not None:
        return PagePolicyStateOut(
            id=page_row.id,
            org_id=org_id,
            scope_type=PolicyScopeType.PAGE,
            scope_id=str(page_id),
            state=parse_policy_state(page_row.state),
            updated_at=page_row.updated_at,
            is_explicit_override=True,
            inherited_from=None,
        )
    if global_row is not None:
        return PagePolicyStateOut(
            id=None,
            org_id=org_id,
            scope_type=PolicyScopeType.PAGE,
            scope_id=str(page_id),
            state=parse_policy_state(global_row.state),
            updated_at=global_row.updated_at,
            is_explicit_override=False,
            inherited_from="global",
        )
    default = PolicyStateDocument()
    return PagePolicyStateOut(
        id=None,
        org_id=org_id,
        scope_type=PolicyScopeType.PAGE,
        scope_id=str(page_id),
        state=default,
        updated_at=None,
        is_explicit_override=False,
        inherited_from="default",
    )


def resolve_page_policy_for_read(
    db: Session, org_id: uuid.UUID, page_id: uuid.UUID
) -> PagePolicyStateOut:
    page_row = fetch_policy_row(
        db,
        org_id,
        policy_key_value=policy_key(PolicyScopeType.PAGE, scope_id=str(page_id)),
    )
    global_row = fetch_policy_row(db, org_id, policy_key_value=policy_key(PolicyScopeType.GLOBAL))
    return build_page_policy_view(
        org_id=org_id,
        page_id=page_id,
        page_row=page_row,
        global_row=global_row,
    )
