"""Asset request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssetCreate(BaseModel):
    asset_class: str
    storage_uri: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class AssetOut(BaseModel):
    id: uuid.UUID
    asset_class: str
    storage_uri: str
    metadata_: dict[str, Any] = Field(alias="metadata")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class SignedDownloadOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_uri: str
    url: str
    expires_at: datetime


class AssetDetailOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: uuid.UUID
    org_id: uuid.UUID
    asset_class: str
    status: str
    source: str
    storage_uri: str
    asset_key: str | None
    asset_key_hash: str | None
    content_hash: str | None
    metadata_: dict[str, Any] = Field(alias="metadata")
    canonical_params: dict[str, Any] | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    download: SignedDownloadOut
    created_at: datetime
