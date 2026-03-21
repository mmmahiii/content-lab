"""Storage integrity verification runs (checksum / existence probes)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.asset import Asset
    from content_lab_api.models.org import Org


class StorageIntegrityCheck(Base):
    __tablename__ = "storage_integrity_checks"
    __table_args__ = (Index("ix_storage_integrity_checks_org_id_status", "org_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    check_kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, default=None
    )
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    org: Mapped[Org | None] = relationship(
        back_populates="storage_integrity_checks", init=False, default=None
    )
    asset: Mapped[Asset | None] = relationship(
        back_populates="storage_integrity_checks", init=False, default=None
    )
