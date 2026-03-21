"""Audio metadata linked to assets (optional; core factory does not depend on this table)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from content_lab_api.db import Base


class AudioTrack(Base):
    """Technical audio descriptors for a media asset."""

    __tablename__ = "audio"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    channel_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, default=None)
    codec: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
