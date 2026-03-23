"""Durable task records for idempotent execution units."""

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
    from content_lab_api.models.provider_job import ProviderJob
    from content_lab_api.models.run import Run


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("org_id", "idempotency_key", name="uq_tasks_org_idempotency_key"),
        Index("ix_tasks_org_id", "org_id"),
        Index("ix_tasks_run_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    task_type: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, default=None
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    org: Mapped[Org | None] = relationship(back_populates="tasks", init=False)
    run: Mapped[Run | None] = relationship(back_populates="tasks", init=False)
    provider_jobs: Mapped[list[ProviderJob]] = relationship(
        "ProviderJob", back_populates="task", init=False, default_factory=list
    )
