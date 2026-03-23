"""Provider-side job tracking; external refs are unique per provider."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.org import Org
    from content_lab_api.models.task import Task


class ProviderJob(Base):
    __tablename__ = "provider_jobs"
    __table_args__ = (
        UniqueConstraint("provider", "external_ref", name="uq_provider_jobs_provider_external_ref"),
        Index("ix_provider_jobs_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(64))
    external_ref: Mapped[str] = mapped_column(String(512))
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    org: Mapped[Org | None] = relationship(back_populates="provider_jobs", init=False)
    task: Mapped[Task | None] = relationship(back_populates="provider_jobs", init=False)
