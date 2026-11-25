"""Quick Reel "Send to Review": save a finished Quick Reel into the page's review flow.

The review flow already exists: generated reels in ``ready`` status are listed by
``GET /orgs/{org}/pages/{page}/reels?status=ready`` and approved / archived / marked posted
by the reels routes. This endpoint only adds the write side for Quick Reel:

- the reel is re-composed here from the hook, branch set and selection (``compose_reel``
  is deterministic and makes no LLM call), so what is stored is what the API itself would
  compose for those choices, not whatever the client sent;
- every Quick Reel for a page goes into one reel family ("Quick Reel", tagged
  ``source=quick_reel``), created on first use;
- the reel is created as a generated reel in ``ready`` so it can be approved. Pipeline QA
  does not run on Quick Reels (they render through Remotion, not FFmpeg); the stored
  metadata says so, and carries the Remotion overlay trace status when an MP4 was rendered.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import insert
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models.asset import Asset
from content_lab_api.models.audit_log import AuditLog
from content_lab_api.models.org import Org
from content_lab_api.models.page import Page
from content_lab_api.models.reel import GeneratedReelStatus, Reel, ReelOrigin
from content_lab_api.models.reel_family import ReelFamily
from content_lab_api.schemas.reel_families import ReelFamilyMode, dump_reel_family_metadata
from content_lab_api.schemas.reels import ReelOut, reel_to_out
from content_lab_creative.generation import (
    BranchSelection,
    BranchSet,
    CreativePageContext,
    HookCandidate,
    compose_reel,
)
from content_lab_shared.logging import ANONYMOUS_ACTOR

router = APIRouter(tags=["quick-reel"])

QUICK_REEL_SOURCE = "quick_reel"
QUICK_REEL_FAMILY_NAME = "Quick Reel"
QUICK_REEL_METADATA_KEY = "quick_reel"


class QuickReelVisualIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    fit: Literal["cutout", "cover"] = "cutout"


class QuickReelRenderIn(BaseModel):
    """The local Remotion render the operator exported, if any."""

    model_config = ConfigDict(extra="forbid")

    render_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")
    duration_seconds: float = Field(gt=0, le=90)
    width: int = Field(ge=16, le=4096)
    height: int = Field(ge=16, le=4096)
    fps: int = Field(ge=1, le=60)
    overlay_trace_status: Literal["pass", "fail"]


class QuickReelSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: HookCandidate
    branches: BranchSet
    selection: BranchSelection
    duration_seconds: int | None = Field(default=None, ge=8, le=60)
    topic: str | None = Field(default=None, max_length=200)
    caption: str = Field(min_length=1, max_length=2_200)
    visuals: list[QuickReelVisualIn] = Field(default_factory=list, max_length=12)
    render: QuickReelRenderIn | None = None
    generation_source: Literal["llm", "fallback"] | None = None
    # Lets the UI retry a send without creating a second reel.
    client_request_id: uuid.UUID | None = None


def _actor(request: Request) -> tuple[str | None, str]:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    return actor_id, ("anonymous" if actor_id is None else "request_header")


def _audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    actor_id, actor_type = _actor(request)
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action=action,
            resource_type=resource_type,
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(resource_id),
            payload=payload,
        )
    )


def _quick_reel_family(
    db: Session, request: Request, *, org_id: uuid.UUID, page_id: uuid.UUID
) -> ReelFamily:
    family = (
        db.query(ReelFamily)
        .filter(
            ReelFamily.org_id == org_id,
            ReelFamily.page_id == page_id,
            ReelFamily.metadata_["source"].astext == QUICK_REEL_SOURCE,
        )
        .order_by(ReelFamily.created_at, ReelFamily.id)
        .first()
    )
    if family is not None:
        return family
    family = ReelFamily(
        org_id=org_id,
        page_id=page_id,
        name=QUICK_REEL_FAMILY_NAME,
        metadata_=dump_reel_family_metadata(ReelFamilyMode.EXPLORE, {"source": QUICK_REEL_SOURCE}),
    )
    db.add(family)
    db.flush()
    _audit(
        db,
        request,
        org_id=org_id,
        action="reel_family.created",
        resource_type="reel_family",
        resource_id=family.id,
        payload={"page_id": str(page_id), "name": family.name, "source": QUICK_REEL_SOURCE},
    )
    return family


def _variant_label(selection: BranchSelection) -> str:
    return f"quick:{selection.structure}/{selection.energy}/{selection.ending}"[:64]


@router.post(
    "/orgs/{org_id}/pages/{page_id}/quick-reel/reels",
    response_model=ReelOut,
    status_code=status.HTTP_201_CREATED,
)
def send_quick_reel_to_review(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    body: QuickReelSaveIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> ReelOut:
    if db.get(Org, org_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    page = db.query(Page).filter(Page.org_id == org_id, Page.id == page_id).one_or_none()
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    context = CreativePageContext.from_page(
        display_name=page.display_name, handle=page.handle, metadata=page.metadata_
    )
    try:
        composed = compose_reel(
            hook=body.hook,
            branches=body.branches,
            selection=body.selection,
            duration_seconds=body.duration_seconds,
            constraints=context.constraints,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    asset_ids = {visual.asset_id for visual in body.visuals}
    if asset_ids:
        found = {
            row[0]
            for row in db.query(Asset.id).filter(Asset.org_id == org_id, Asset.id.in_(asset_ids))
        }
        missing = sorted(str(asset_id) for asset_id in asset_ids - found)
        if missing:
            raise HTTPException(
                status_code=422, detail=f"Unknown asset(s) for this org: {', '.join(missing)}"
            )

    family = _quick_reel_family(db, request, org_id=org_id, page_id=page_id)

    if body.client_request_id is not None:
        existing = (
            db.query(Reel)
            .filter(
                Reel.reel_family_id == family.id,
                Reel.metadata_[QUICK_REEL_METADATA_KEY]["client_request_id"].astext
                == str(body.client_request_id),
            )
            .first()
        )
        if existing is not None:
            db.commit()
            response.status_code = status.HTTP_200_OK
            return reel_to_out(existing, page_id=page_id)

    actor_id, _ = _actor(request)
    metadata: dict[str, Any] = {
        "source": QUICK_REEL_SOURCE,
        QUICK_REEL_METADATA_KEY: {
            "schema_version": 1,
            "topic": body.topic,
            "hook": body.hook.model_dump(mode="json"),
            "selection": body.selection.model_dump(mode="json"),
            "branches": body.branches.model_dump(mode="json"),
            "composed": composed.model_dump(mode="json"),
            "caption": body.caption.strip(),
            "visuals": [visual.model_dump(mode="json") for visual in body.visuals],
            "render": None if body.render is None else body.render.model_dump(mode="json"),
            "generation_source": body.generation_source,
            "client_request_id": (
                None if body.client_request_id is None else str(body.client_request_id)
            ),
            "sent_by": actor_id,
            "qa": {
                "status": "not_run",
                "reason": "Quick Reel renders through Remotion; pipeline QA is not wired to it yet.",
                "overlay_trace_status": (
                    None if body.render is None else body.render.overlay_trace_status
                ),
            },
        },
    }
    reel = Reel(
        org_id=org_id,
        reel_family_id=family.id,
        origin=ReelOrigin.GENERATED.value,
        status=GeneratedReelStatus.READY.value,
        variant_label=_variant_label(body.selection),
        metadata_=metadata,
    )
    db.add(reel)
    try:
        db.flush()
        _audit(
            db,
            request,
            org_id=org_id,
            action="reel.created",
            resource_type="reel",
            resource_id=reel.id,
            payload={
                "page_id": str(page_id),
                "family_id": str(family.id),
                "origin": reel.origin,
                "status": reel.status,
                "variant_label": reel.variant_label,
                "source": QUICK_REEL_SOURCE,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(reel)
    return reel_to_out(reel, page_id=page_id)


__all__ = ["router"]
