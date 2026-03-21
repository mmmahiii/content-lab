"""Org-scoped durable policy snapshots (rate limits, kill switches, etc.)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.org import Org


class PolicyState(Base):
    __tablename__ = "policy_state"
    __table_args__ = (
        UniqueConstraint("org_id", "policy_key", name="uq_policy_state_org_policy_key"),
        Index("ix_policy_state_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    policy_key: Mapped[str] = mapped_column(String(128))
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    org: Mapped[Org | None] = relationship(back_populates="policy_states", init=False, default=None)
