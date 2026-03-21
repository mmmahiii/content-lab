"""Reel family ORM model (shared context for generated variants)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.page import Page
    from content_lab_api.models.reel import Reel


class ReelFamily(Base):
    __tablename__ = "reel_families"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(512))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    page: Mapped[Page] = relationship("Page", back_populates="reel_families", init=False)
    reels: Mapped[list[Reel]] = relationship(
        "Reel", back_populates="reel_family", init=False, default_factory=list
    )
