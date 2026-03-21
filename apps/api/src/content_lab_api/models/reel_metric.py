"""Reel-level metrics snapshots (optional intelligence; not required for package generation)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from content_lab_api.db import Base


class ReelMetric(Base):
    """Point-in-time metrics for a workflow run (e.g. engagement or quality scores)."""

    __tablename__ = "reel_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    extractor_version: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
