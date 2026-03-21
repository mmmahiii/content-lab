"""Social page ORM model (owned portfolio accounts vs competitors)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.reel_family import ReelFamily


class PageKind(str, enum.Enum):
    OWNED = "owned"
    COMPETITOR = "competitor"


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(512))
    external_page_id: Mapped[str | None] = mapped_column(String(256), default=None)
    handle: Mapped[str | None] = mapped_column(String(256), default=None)
    kind: Mapped[str] = mapped_column(String(32), default=PageKind.OWNED.value)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    reel_families: Mapped[list[ReelFamily]] = relationship(
        "ReelFamily", back_populates="page", init=False, default_factory=list
    )
