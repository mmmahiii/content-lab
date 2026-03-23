"""Owned-page, policy, and reel-creation helpers for the daily reel factory."""

from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from content_lab_api.models.page import Page, PageKind
from content_lab_api.models.policy_state import PolicyState
from content_lab_api.models.reel import GeneratedReelStatus, Reel
from content_lab_api.models.reel_family import ReelFamily
from content_lab_api.schemas.pages import parse_page_metadata
from content_lab_api.schemas.policy import (
    PolicyScopeType,
    PolicyStateDocument,
    dump_policy_state,
    parse_policy_state,
)
from content_lab_api.schemas.reel_families import ReelFamilyMode, dump_reel_family_metadata


@dataclass(frozen=True, slots=True)
class FactoryOwnedPage:
    """Owned page record exposed to the phase-1 factory orchestration layer."""

    org_id: uuid.UUID
    page_id: uuid.UUID
    display_name: str
    platform: str
    handle: str | None
    content_pillars: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FactoryPolicyBundle:
    """Global/page policy bundle with the effective merged state."""

    global_policy: PolicyStateDocument
    page_policy: PolicyStateDocument | None
    effective_policy: PolicyStateDocument


def _policy_key(scope_type: PolicyScopeType, *, scope_id: str | None = None) -> str:
    if scope_type is PolicyScopeType.GLOBAL:
        return PolicyScopeType.GLOBAL.value
    assert scope_id is not None
    return f"{scope_type.value}:{scope_id}"


def _deep_merge_state(
    base: dict[str, Any],
    overlay: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = deepcopy(base)
    if overlay is None:
        return merged

    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_state(existing, value)
            continue
        merged[key] = deepcopy(value)
    return merged


def list_owned_pages(
    db: Session,
    *,
    org_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[FactoryOwnedPage]:
    """Return owned pages in stable order for phase-1 planning."""

    query = db.query(Page).filter(Page.kind == PageKind.OWNED.value)
    if org_id is not None:
        query = query.filter(Page.org_id == org_id)
    pages = query.order_by(Page.created_at.asc(), Page.id.asc())
    if limit is not None:
        pages = pages.limit(limit)

    owned_pages: list[FactoryOwnedPage] = []
    for page in pages.all():
        page_metadata = parse_page_metadata(page.metadata_)
        content_pillars = (
            tuple(page_metadata.persona.content_pillars)
            if page_metadata.persona is not None
            else ()
        )
        owned_pages.append(
            FactoryOwnedPage(
                org_id=page.org_id,
                page_id=page.id,
                display_name=page.display_name,
                platform=page.platform,
                handle=page.handle,
                content_pillars=content_pillars,
            )
        )
    return owned_pages


def load_policy_bundle(
    db: Session,
    *,
    org_id: uuid.UUID,
    page_id: uuid.UUID,
) -> FactoryPolicyBundle:
    """Load the effective global/page policy bundle for a page."""

    global_row = (
        db.query(PolicyState)
        .filter(
            PolicyState.org_id == org_id,
            PolicyState.policy_key == _policy_key(PolicyScopeType.GLOBAL),
        )
        .one_or_none()
    )
    page_row = (
        db.query(PolicyState)
        .filter(
            PolicyState.org_id == org_id,
            PolicyState.policy_key == _policy_key(PolicyScopeType.PAGE, scope_id=str(page_id)),
        )
        .one_or_none()
    )

    global_policy = parse_policy_state(None if global_row is None else global_row.state)
    page_policy = None if page_row is None else parse_policy_state(page_row.state)
    effective_payload = _deep_merge_state(
        dump_policy_state(global_policy),
        None if page_row is None else dict(page_row.state or {}),
    )

    return FactoryPolicyBundle(
        global_policy=global_policy,
        page_policy=page_policy,
        effective_policy=PolicyStateDocument.model_validate(effective_payload),
    )


def create_reel_family(
    db: Session,
    *,
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    name: str,
    mode: ReelFamilyMode,
    metadata: dict[str, Any],
) -> ReelFamily:
    """Create a reel family row for the phase-1 factory."""

    family = ReelFamily(
        org_id=org_id,
        page_id=page_id,
        name=name,
        metadata_=dump_reel_family_metadata(mode, metadata),
    )
    db.add(family)
    db.flush()
    return family


def create_reel_variant(
    db: Session,
    *,
    org_id: uuid.UUID,
    family_id: uuid.UUID,
    variant_label: str,
    metadata: dict[str, Any],
    status: GeneratedReelStatus = GeneratedReelStatus.PLANNING,
) -> Reel:
    """Create a generated reel row ready for ``process_reel`` dispatch."""

    reel = Reel(
        org_id=org_id,
        reel_family_id=family_id,
        status=status.value,
        variant_label=variant_label,
        metadata_=dict(metadata),
    )
    db.add(reel)
    db.flush()
    return reel
