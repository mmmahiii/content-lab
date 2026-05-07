"""Performance rollups for reusable asset combinations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from content_lab_api.db import Base


class AssetCombinationPerformance(Base):
    """Metric aggregates for a deterministic group of assets used together."""

    __tablename__ = "asset_combination_performance"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "combination_key",
            name="uq_asset_combination_performance_org_key",
        ),
        Index("ix_asset_combination_performance_org_sample_count", "org_id", "sample_count"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    combination_key: Mapped[str] = mapped_column(String(512))
    component_roles: Mapped[list[str]] = mapped_column(JSONB, default_factory=list)
    asset_ids: Mapped[list[str]] = mapped_column(JSONB, default_factory=list)
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
