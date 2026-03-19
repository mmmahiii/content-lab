"""Asset request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AssetCreate(BaseModel):
    kind: str
    storage_key: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class AssetOut(BaseModel):
    id: uuid.UUID
    kind: str
    storage_key: str
    metadata_: dict[str, Any] = Field(alias="metadata")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
