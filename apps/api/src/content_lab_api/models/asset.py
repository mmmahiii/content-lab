"""Asset ORM model.

pgvector column uses Vector type from the pgvector extension; make sure
CREATE EXTENSION IF NOT EXISTS vector; has been run (handled by the initial Alembic migration).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.asset_family import AssetFamily
    from content_lab_api.models.asset_gen_param import AssetGenParam
    from content_lab_api.models.asset_usage import AssetUsage
    from content_lab_api.models.run_asset import RunAsset
    from content_lab_api.models.storage_integrity_check import StorageIntegrityCheck

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index(
            "uq_assets_org_asset_key",
            "org_id",
            "asset_key",
            unique=True,
            postgresql_where=text("asset_key IS NOT NULL"),
        ),
        Index(
            "uq_assets_org_asset_key_hash",
            "org_id",
            "asset_key_hash",
            unique=True,
            postgresql_where=text("asset_key_hash IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    asset_class: Mapped[str] = mapped_column(String(64))
    storage_uri: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(64), default="unknown")
    asset_key: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    phash: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(32), default="active")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default_factory=dict)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536) if Vector else Text, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    family_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_families.id", ondelete="SET NULL"), nullable=True, default=None
    )
    asset_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)

    family: Mapped[AssetFamily | None] = relationship(
        "AssetFamily", back_populates="assets", init=False, default=None
    )
    gen_params: Mapped[list[AssetGenParam]] = relationship(
        "AssetGenParam", back_populates="asset", init=False, default_factory=list
    )
    asset_usages: Mapped[list[AssetUsage]] = relationship(
        "AssetUsage", back_populates="asset", init=False, default_factory=list
    )
    run_assets: Mapped[list[RunAsset]] = relationship(
        "RunAsset", back_populates="asset", init=False, default_factory=list
    )
    storage_integrity_checks: Mapped[list[StorageIntegrityCheck]] = relationship(
        "StorageIntegrityCheck", back_populates="asset", init=False, default_factory=list
    )
