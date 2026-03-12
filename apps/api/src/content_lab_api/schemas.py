"""Pydantic schemas for API request/response payloads."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AssetCreate(BaseModel):
    kind: str
    storage_key: str
    metadata_: dict = Field(default_factory=dict, alias="metadata")


class AssetOut(BaseModel):
    id: uuid.UUID
    kind: str
    storage_key: str
    metadata_: dict = Field(alias="metadata")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class RunCreate(BaseModel):
    name: str
    config: dict = Field(default_factory=dict)


class RunOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    config: dict
    result: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OutboxEventOut(BaseModel):
    id: uuid.UUID
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict
    published: bool
    created_at: datetime

    model_config = {"from_attributes": True}
