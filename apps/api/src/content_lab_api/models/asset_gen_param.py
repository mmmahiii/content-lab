"""Persisted canonical generation parameters / AssetKey history per asset."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.asset import Asset


class AssetGenParam(Base):
    """Ordered history of generation parameters for an asset (provenance / audit)."""

    __tablename__ = "asset_gen_params"
    __table_args__ = (UniqueConstraint("asset_id", "seq", name="uq_asset_gen_params_asset_seq"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    asset_key_hash: Mapped[str] = mapped_column(String(64))
    canonical_params: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    asset: Mapped[Asset | None] = relationship(
        "Asset", back_populates="gen_params", init=False, default=None
    )
