"""Join between workflow runs and assets (legacy table name: run_assets)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.asset import Asset
    from content_lab_api.models.run import Run


class RunAsset(Base):
    """Links an asset to a run; kept under the historical table name for compatibility."""

    __tablename__ = "run_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    asset_role: Mapped[str] = mapped_column(String(64))

    run: Mapped[Run | None] = relationship(back_populates="run_assets", init=False, default=None)
    asset: Mapped[Asset | None] = relationship(
        back_populates="run_assets", init=False, default=None
    )
