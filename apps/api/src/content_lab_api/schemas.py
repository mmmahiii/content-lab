"""Pydantic schemas for API request/response payloads."""

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


class RunCreate(BaseModel):
    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class RunOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    config: dict[str, Any]
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OutboxEventOut(BaseModel):
    id: uuid.UUID
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    published: bool
    created_at: datetime

    model_config = {"from_attributes": True}
