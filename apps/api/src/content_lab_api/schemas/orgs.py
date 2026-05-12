"""Organization response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from content_lab_api.models.org import Org

__all__ = ["OrgOut", "org_to_out"]


class OrgOut(BaseModel):
    """Public organization summary for operator tooling."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    page_count: int = 0


def org_to_out(org: Org, *, page_count: int = 0) -> OrgOut:
    return OrgOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        created_at=org.created_at,
        page_count=page_count,
    )
