"""Base domain model providing common fields for all Content Lab entities."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex


class DomainModel(BaseModel):
    """Base class for all Content Lab domain models.

    Provides a unique ``id`` and ``created_at``/``updated_at`` timestamps.
    Subclasses add domain-specific fields.
    """

    id: str = Field(default_factory=_new_id)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
