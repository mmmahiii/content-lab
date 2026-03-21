"""Run ORM model (workflow execution aggregate)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.run_asset import RunAsset


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    workflow_key: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    input_params: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
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
