"""Experiment assignments (feature flags / A-B) keyed by org and subject."""

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


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "experiment_key",
            "subject_type",
            "subject_id",
            name="uq_experiments_org_experiment_subject",
        ),
        Index("ix_experiments_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    experiment_key: Mapped[str] = mapped_column(String(128))
    variant: Mapped[str] = mapped_column(String(64))
    subject_type: Mapped[str] = mapped_column(String(64))
    subject_id: Mapped[str] = mapped_column(String(256))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    org: Mapped[Org | None] = relationship(back_populates="experiments", init=False)
