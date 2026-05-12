"""Organization discovery routes for operator tooling."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models.org import Org
from content_lab_api.models.page import Page
from content_lab_api.schemas.orgs import OrgOut, org_to_out

router = APIRouter(prefix="/orgs", tags=["orgs"])


@router.get("", response_model=list[OrgOut])
def list_orgs(db: Session = Depends(get_db)) -> list[OrgOut]:
    page_counts = dict(
        db.query(Page.org_id, func.count(Page.id))
        .group_by(Page.org_id)
        .all()
    )
    orgs = db.query(Org).order_by(Org.created_at.desc(), Org.id.desc()).all()
    return [org_to_out(org, page_count=page_counts.get(org.id, 0)) for org in orgs]
