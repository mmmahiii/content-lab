"""Asset ORM model.

pgvector column uses Vector type from the pgvector extension; make sure
CREATE EXTENSION IF NOT EXISTS vector; has been run (handled by the initial Alembic migration).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.run_asset import RunAsset

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    asset_class: Mapped[str] = mapped_column(String(64))
    storage_uri: Mapped[str] = mapped_column(String(512))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default_factory=dict)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536) if Vector else Text, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    run_assets: Mapped[list[RunAsset]] = relationship(
        "RunAsset", back_populates="asset", init=False, default_factory=list
    )
