"""Correlational performance rollups for component assets."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from content_lab_api.db import Base


class AssetPerformanceSummary(Base):
    """Metric aggregates for an asset used in a specific component role."""

    __tablename__ = "asset_performance_summaries"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "asset_id",
            "component_role",
            name="uq_asset_performance_summaries_org_asset_role",
        ),
        Index("ix_asset_performance_summaries_org_role", "org_id", "component_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    component_role: Mapped[str] = mapped_column(String(64))
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    metric_totals: Mapped[dict[str, float]] = mapped_column(JSONB, default_factory=dict)
    metric_averages: Mapped[dict[str, float]] = mapped_column(JSONB, default_factory=dict)
    last_metric_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    attribution_note: Mapped[str] = mapped_column(
        String(128), default="correlational_not_causal"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )
