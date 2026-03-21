"""User ORM model (identity for future auth / RBAC)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.org_membership import OrgMembership


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    memberships: Mapped[list[OrgMembership]] = relationship(
        back_populates="user", init=False, default_factory=list
    )
