"""OutboxEvent ORM model (transactional outbox for reliable dispatch)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from content_lab_api.db import Base


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_dispatch_queue",
            "next_attempt_at",
            "created_at",
            postgresql_where=text("delivery_status IN ('pending', 'failed')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    aggregate_type: Mapped[str] = mapped_column(String(128))
    aggregate_id: Mapped[str] = mapped_column(String(256))
    event_type: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    delivery_status: Mapped[str] = mapped_column(String(32), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
