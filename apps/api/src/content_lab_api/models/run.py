"""Run and RunAsset ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.asset import Asset


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    run_assets: Mapped[list[RunAsset]] = relationship(
        back_populates="run", init=False, default_factory=list
    )


class RunAsset(Base):
    __tablename__ = "run_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    role: Mapped[str] = mapped_column(String(64))

    run: Mapped[Run | None] = relationship(back_populates="run_assets", init=False, default=None)
    asset: Mapped[Asset | None] = relationship(
        back_populates="run_assets", init=False, default=None
    )
