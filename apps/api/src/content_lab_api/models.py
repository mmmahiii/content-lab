"""SQLAlchemy ORM models for Content Lab.

pgvector column uses Vector type from the pgvector extension; make sure
CREATE EXTENSION IF NOT EXISTS vector; has been run (handled by the initial Alembic migration).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # allow import when pgvector wheel is absent (tests, linting)
    Vector = None  # type: ignore[assignment,misc]


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    kind: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default_factory=dict)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536) if Vector else Text, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    run_assets: Mapped[list[RunAsset]] = relationship(back_populates="asset", default_factory=list)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    config: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    run_assets: Mapped[list[RunAsset]] = relationship(back_populates="run", default_factory=list)


class RunAsset(Base):
    __tablename__ = "run_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    role: Mapped[str] = mapped_column(String(64))

    run: Mapped[Run] = relationship(back_populates="run_assets", default=None)
    asset: Mapped[Asset] = relationship(back_populates="run_assets", default=None)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    aggregate_type: Mapped[str] = mapped_column(String(128))
    aggregate_id: Mapped[str] = mapped_column(String(256))
    event_type: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    published: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
