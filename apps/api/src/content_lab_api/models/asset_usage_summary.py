"""Asset-level usage rollups for reuse and cooldown policy inputs."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from content_lab_api.db import Base


class AssetUsageSummary(Base):
    """Current aggregate usage counters for one asset within an org."""

    __tablename__ = "asset_usage_summaries"
    __table_args__ = (
        UniqueConstraint("org_id", "asset_id", name="uq_asset_usage_summaries_org_asset"),
        Index("ix_asset_usage_summaries_org_last_used", "org_id", "last_used_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    reuse_count: Mapped[int] = mapped_column(Integer, default=0)
    used_in_reel_count: Mapped[int] = mapped_column(Integer, default=0)
    used_in_pack_count: Mapped[int] = mapped_column(Integer, default=0)
    used_as_component_role_counts: Mapped[dict[str, int]] = mapped_column(
        JSONB, default_factory=dict
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )
