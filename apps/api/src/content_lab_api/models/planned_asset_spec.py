"""Planned asset specs that describe intent before assets exist."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.asset_pack import AssetPack
    from content_lab_api.models.asset_pack_item import AssetPackItem


class PlannedAssetSpecStatus(str, enum.Enum):
    """Lifecycle for an intended reusable asset before and after creation."""

    DRAFT = "draft"
    PLANNED = "planned"
    GENERATING = "generating"
    GENERATED = "generated"
    REGISTERED = "registered"
    FAILED = "failed"
    ARCHIVED = "archived"


PLANNED_ASSET_SPEC_STATUSES: Final[frozenset[str]] = frozenset(
    s.value for s in PlannedAssetSpecStatus
)

PLANNED_ASSET_SPEC_STATUS_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    PlannedAssetSpecStatus.DRAFT.value: frozenset(
        {PlannedAssetSpecStatus.PLANNED.value, PlannedAssetSpecStatus.ARCHIVED.value}
    ),
    PlannedAssetSpecStatus.PLANNED.value: frozenset(
        {
            PlannedAssetSpecStatus.GENERATING.value,
            PlannedAssetSpecStatus.FAILED.value,
            PlannedAssetSpecStatus.ARCHIVED.value,
        }
    ),
    PlannedAssetSpecStatus.GENERATING.value: frozenset(
        {
            PlannedAssetSpecStatus.GENERATED.value,
            PlannedAssetSpecStatus.FAILED.value,
        }
    ),
    PlannedAssetSpecStatus.GENERATED.value: frozenset(
        {PlannedAssetSpecStatus.REGISTERED.value, PlannedAssetSpecStatus.ARCHIVED.value}
    ),
    PlannedAssetSpecStatus.REGISTERED.value: frozenset({PlannedAssetSpecStatus.ARCHIVED.value}),
    PlannedAssetSpecStatus.FAILED.value: frozenset(
        {PlannedAssetSpecStatus.PLANNED.value, PlannedAssetSpecStatus.ARCHIVED.value}
    ),
    PlannedAssetSpecStatus.ARCHIVED.value: frozenset(),
}


def validate_planned_asset_spec_status_transition(current: str, next_status: str) -> None:
    """Application-level transition guard for planned asset specs."""

    if current not in PLANNED_ASSET_SPEC_STATUSES:
        msg = f"Invalid planned asset spec status {current!r}"
        raise ValueError(msg)
    if next_status not in PLANNED_ASSET_SPEC_STATUSES:
        msg = f"Invalid planned asset spec status {next_status!r}"
        raise ValueError(msg)
    if next_status == current:
        return
    if next_status not in PLANNED_ASSET_SPEC_STATUS_TRANSITIONS[current]:
        msg = f"Invalid planned asset spec status transition {current!r} -> {next_status!r}"
        raise ValueError(msg)


class PlannedAssetSpec(Base):
    __tablename__ = "planned_asset_specs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'planned', 'generating', 'generated', 'registered', "
            "'failed', 'archived')",
            name="ck_planned_asset_specs_status",
        ),
        CheckConstraint(
            "priority >= 0",
            name="ck_planned_asset_specs_priority_nonnegative",
        ),
        CheckConstraint(
            "estimated_reuse_count >= 0",
            name="ck_planned_asset_specs_estimated_reuse_count_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    asset_pack_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_packs.id", ondelete="CASCADE")
    )
    asset_kind: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(64))
    working_title: Mapped[str] = mapped_column(String(256))
    purpose: Mapped[str] = mapped_column(Text)
    prompt_or_description: Mapped[str] = mapped_column(Text)
    required_traits: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    compatible_with: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    compatibility_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default_factory=dict)
    intended_reel_formats: Mapped[list[str]] = mapped_column(JSONB, default_factory=list)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    estimated_reuse_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default=PlannedAssetSpecStatus.DRAFT.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    asset_pack: Mapped[AssetPack | None] = relationship(
        "AssetPack", back_populates="planned_asset_specs", init=False
    )
    asset_pack_items: Mapped[list[AssetPackItem]] = relationship(
        "AssetPackItem",
        back_populates="planned_asset_spec",
        init=False,
        default_factory=list,
    )
