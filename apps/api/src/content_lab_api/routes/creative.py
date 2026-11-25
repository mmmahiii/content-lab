"""Org/page-scoped creative generation: hooks and Quick Reel branches.

These endpoints are stateless: they read the page for context, call the LLM (or the
deterministic fallback) and return the result. Nothing is persisted.
"""

from __future__ import annotations

import uuid

from content_lab_intelligence import LLMClient
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db, get_llm_client
from content_lab_api.models.page import Page
from content_lab_creative.generation import (
    BranchGenerationRequest,
    BranchGenerationResult,
    BranchSelection,
    BranchSet,
    ChoiceMoment,
    ComposedReel,
    CreativePageContext,
    HookCandidate,
    HookGenerationRequest,
    HookGenerationResult,
    compose_reel,
    generate_branches,
    generate_hooks,
)

router = APIRouter(tags=["creative"])


class HookRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str | None = Field(default=None, max_length=200)
    asset_labels: list[str] = Field(default_factory=list, max_length=60)
    count: int = Field(default=3, ge=2, le=5)
    niche: str | None = Field(default=None, max_length=120)


class BranchRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: HookCandidate
    topic: str | None = Field(default=None, max_length=200)
    asset_labels: list[str] = Field(default_factory=list, max_length=60)
    duration_seconds: int = Field(default=15, ge=8, le=60)
    moments: list[ChoiceMoment] = Field(default_factory=lambda: list(ChoiceMoment))
    options_per_moment: int = Field(default=3, ge=2, le=3)
    niche: str | None = Field(default=None, max_length=120)


class ComposeRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: HookCandidate
    branches: BranchSet
    selection: BranchSelection
    duration_seconds: int | None = Field(default=None, ge=8, le=60)


def _page_context(
    db: Session, *, org_id: uuid.UUID, page_id: uuid.UUID, niche: str | None = None
) -> CreativePageContext:
    page = db.get(Page, page_id)
    if page is None or page.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return CreativePageContext.from_page(
        display_name=page.display_name,
        handle=page.handle,
        metadata=page.metadata_,
        niche=niche,
    )


@router.post("/orgs/{org_id}/pages/{page_id}/hooks", response_model=HookGenerationResult)
def generate_page_hooks(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    body: HookRequestIn,
    db: Session = Depends(get_db),
    llm_client: LLMClient | None = Depends(get_llm_client),
) -> HookGenerationResult:
    page = _page_context(db, org_id=org_id, page_id=page_id, niche=body.niche)
    return generate_hooks(
        HookGenerationRequest(
            page=page, topic=body.topic, asset_labels=body.asset_labels, count=body.count
        ),
        client=llm_client,
    )


@router.post(
    "/orgs/{org_id}/pages/{page_id}/quick-reel/branches",
    response_model=BranchGenerationResult,
)
def generate_quick_reel_branches(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    body: BranchRequestIn,
    db: Session = Depends(get_db),
    llm_client: LLMClient | None = Depends(get_llm_client),
) -> BranchGenerationResult:
    page = _page_context(db, org_id=org_id, page_id=page_id, niche=body.niche)
    try:
        request = BranchGenerationRequest(
            page=page,
            hook=body.hook,
            topic=body.topic,
            asset_labels=body.asset_labels,
            duration_seconds=body.duration_seconds,
            moments=body.moments,
            options_per_moment=body.options_per_moment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return generate_branches(request, client=llm_client)


@router.post("/orgs/{org_id}/pages/{page_id}/quick-reel/compose", response_model=ComposedReel)
def compose_quick_reel(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    body: ComposeRequestIn,
    db: Session = Depends(get_db),
) -> ComposedReel:
    """Turn one choice per moment into a renderable timeline. No LLM call."""

    page = _page_context(db, org_id=org_id, page_id=page_id)
    try:
        return compose_reel(
            hook=body.hook,
            branches=body.branches,
            selection=body.selection,
            duration_seconds=body.duration_seconds,
            constraints=page.constraints,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
