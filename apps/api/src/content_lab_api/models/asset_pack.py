"""Planned reusable asset packs for a niche or content strategy."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.asset_pack_item import AssetPackItem
    from content_lab_api.models.org import Org
    from content_lab_api.models.planned_asset_spec import PlannedAssetSpec


class AssetPackStatus(str, enum.Enum):
    """Lifecycle for reusable asset pack planning and generation."""

    DRAFT = "draft"
    PLANNED = "planned"
    APPROVED = "approved"
    REJECTED = "rejected"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


ASSET_PACK_STATUSES: Final[frozenset[str]] = frozenset(s.value for s in AssetPackStatus)


class AssetPack(Base):
    __tablename__ = "asset_packs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'planned', 'approved', 'rejected', 'generating', "
            "'ready', 'failed', 'archived')",
            name="ck_asset_packs_status",
        ),
        CheckConstraint(
            "requested_asset_count >= 0",
            name="ck_asset_packs_requested_asset_count_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(256))
    niche: Mapped[str] = mapped_column(String(256))
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    requested_asset_count: Mapped[int] = mapped_column(Integer, default=0)
    asset_mix_requested_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    asset_mix_final_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(String(32), default=AssetPackStatus.DRAFT.value)
    strategy_summary: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    org: Mapped[Org | None] = relationship("Org", back_populates="asset_packs", init=False)
    items: Mapped[list[AssetPackItem]] = relationship(
        "AssetPackItem", back_populates="asset_pack", init=False, default_factory=list
    )
    planned_asset_specs: Mapped[list[PlannedAssetSpec]] = relationship(
        "PlannedAssetSpec",
        back_populates="asset_pack",
        init=False,
        default_factory=list,
    )
