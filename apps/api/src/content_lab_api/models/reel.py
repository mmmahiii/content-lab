"""Reel ORM model (generated variants vs observed external reels)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.reel_family import ReelFamily


class ReelOrigin(str, enum.Enum):
    GENERATED = "generated"
    OBSERVED = "observed"


class GeneratedReelStatus(str, enum.Enum):
    """Canonical generated-reel lifecycle (architecture: draft through ready/posted)."""

    DRAFT = "draft"
    PLANNING = "planning"
    GENERATING = "generating"
    EDITING = "editing"
    QA = "qa"
    QA_FAILED = "qa_failed"
    READY = "ready"
    POSTED = "posted"
    ARCHIVED = "archived"


class ObservedReelStatus(str, enum.Enum):
    """Terminal states for ingested/observed reels only (no factory pipeline)."""

    ACTIVE = "active"
    REMOVED = "removed"
    UNAVAILABLE = "unavailable"


GENERATED_REEL_STATUSES: Final[frozenset[str]] = frozenset(s.value for s in GeneratedReelStatus)
OBSERVED_REEL_STATUSES: Final[frozenset[str]] = frozenset(s.value for s in ObservedReelStatus)


def validate_reel_origin_status(origin: str, status: str) -> None:
    """Application-level invariant aligned with DB CHECK on ``reels``."""

    if origin == ReelOrigin.GENERATED.value:
        if status not in GENERATED_REEL_STATUSES:
            msg = f"Invalid status {status!r} for generated reel"
            raise ValueError(msg)
        return
    if origin == ReelOrigin.OBSERVED.value:
        if status not in OBSERVED_REEL_STATUSES:
            msg = f"Invalid status {status!r} for observed reel"
            raise ValueError(msg)
        return
    msg = f"Invalid reel origin {origin!r}"
    raise ValueError(msg)


class Reel(Base):
    __tablename__ = "reels"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('generated', 'observed')",
            name="ck_reels_origin",
        ),
        CheckConstraint(
            "(origin = 'generated' AND status IN ("
            "'draft', 'planning', 'generating', 'editing', 'qa', "
            "'qa_failed', 'ready', 'posted', 'archived'"
            ")) OR (origin = 'observed' AND status IN ('active', 'removed', 'unavailable'))",
            name="ck_reels_origin_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    reel_family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reel_families.id", ondelete="CASCADE")
    )
    origin: Mapped[str] = mapped_column(String(32), default=ReelOrigin.GENERATED.value)
    status: Mapped[str] = mapped_column(String(32), default=GeneratedReelStatus.DRAFT.value)
    variant_label: Mapped[str | None] = mapped_column(String(64), default=None)
    external_reel_id: Mapped[str | None] = mapped_column(String(256), default=None)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    reel_family: Mapped[ReelFamily] = relationship("ReelFamily", back_populates="reels", init=False)
