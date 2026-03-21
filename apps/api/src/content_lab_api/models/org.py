"""Organization ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.api_key import ApiKey
    from content_lab_api.models.org_membership import OrgMembership


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    name: Mapped[str] = mapped_column(String(256))
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    memberships: Mapped[list[OrgMembership]] = relationship(
        back_populates="org", init=False, default_factory=list
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="org", init=False, default_factory=list
    )
