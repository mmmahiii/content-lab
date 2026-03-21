"""Derived / extracted features with optional embeddings (intelligence phase; optional for phase-1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from content_lab_api.db import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None


class DerivedFeature(Base):
    """Structured feature payload plus an optional vector embedding."""

    __tablename__ = "features"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    feature_kind: Mapped[str] = mapped_column(String(128))
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536) if Vector else Text, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
