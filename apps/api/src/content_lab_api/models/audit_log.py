"""Append-only audit trail for security-sensitive actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.org import Org


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_org_id_created_at", "org_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(128))
    actor_type: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    actor_id: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    resource_id: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    org: Mapped[Org | None] = relationship(back_populates="audit_logs", init=False)
