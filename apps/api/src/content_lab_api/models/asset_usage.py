"""Authoritative join between reels (content) and assets (creative lineage)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.asset import Asset
    from content_lab_api.models.reel import Reel


class AssetUsage(Base):
    """Links an asset to a reel; preferred model for content lineage (vs run_assets)."""

    __tablename__ = "asset_usage"
    __table_args__ = (
        UniqueConstraint(
            "reel_id",
            "asset_id",
            "usage_role",
            name="uq_asset_usage_reel_asset_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    reel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reels.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    usage_role: Mapped[str] = mapped_column(String(64))
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    reel: Mapped[Reel | None] = relationship(
        "Reel", back_populates="asset_usages", init=False, default=None
    )
    asset: Mapped[Asset | None] = relationship(
        "Asset", back_populates="asset_usages", init=False, default=None
    )
