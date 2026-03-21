"""Run ORM model (workflow execution aggregate)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.run_asset import RunAsset
    from content_lab_api.models.task import Task


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index(
            "uq_runs_org_idempotency_key",
            "org_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    workflow_key: Mapped[str] = mapped_column(String(256))
    flow_trigger: Mapped[str] = mapped_column(String(64), default="unknown")
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    external_ref: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    input_params: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    run_metadata: Mapped[dict[str, Any]] = mapped_column(
        "run_metadata", JSONB, default_factory=dict
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    run_assets: Mapped[list[RunAsset]] = relationship(
        "RunAsset", back_populates="run", init=False, default_factory=list
    )
    tasks: Mapped[list[Task]] = relationship(
        "Task", back_populates="run", init=False, default_factory=list
    )
