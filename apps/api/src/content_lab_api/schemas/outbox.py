"""Outbox event response schema."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class OutboxEventOut(BaseModel):
    id: uuid.UUID
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    published: bool
    created_at: datetime

    model_config = {"from_attributes": True}
