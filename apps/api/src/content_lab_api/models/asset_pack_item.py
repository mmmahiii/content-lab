"""Asset pack membership with the intended reusable role."""

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
    from content_lab_api.models.asset import Asset
    from content_lab_api.models.asset_pack import AssetPack
    from content_lab_api.models.planned_asset_spec import PlannedAssetSpec


class AssetPackItemStatus(str, enum.Enum):
    """Planning state for an individual asset pack member."""

    PLANNED = "planned"
    GENERATING = "generating"
    GENERATED = "generated"
    UPLOADED = "uploaded"
    IMPORTED = "imported"
    REUSED = "reused"
    SELECTED = "selected"
    FAILED = "failed"


ASSET_PACK_ITEM_STATUSES: Final[frozenset[str]] = frozenset(
    s.value for s in AssetPackItemStatus
)


class AssetPackItem(Base):
    __tablename__ = "asset_pack_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'generating', 'generated', 'uploaded', 'imported', "
            "'reused', 'selected', 'failed')",
            name="ck_asset_pack_items_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    asset_pack_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_packs.id", ondelete="CASCADE")
    )
    asset_kind: Mapped[str] = mapped_column(String(64))
    pack_role: Mapped[str] = mapped_column(String(128))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, default=None
    )
    planned_asset_spec_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("planned_asset_specs.id", ondelete="SET NULL"), nullable=True, default=None
    )
    reuse_purpose: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default=AssetPackItemStatus.PLANNED.value)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    asset_pack: Mapped[AssetPack | None] = relationship(
        "AssetPack", back_populates="items", init=False
    )
    asset: Mapped[Asset | None] = relationship(
        "Asset", back_populates="asset_pack_items", init=False
    )
    planned_asset_spec: Mapped[PlannedAssetSpec | None] = relationship(
        "PlannedAssetSpec", back_populates="asset_pack_items", init=False
    )
