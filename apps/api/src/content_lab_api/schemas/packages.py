"""Schemas for package retrieval and signed artifact access."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from content_lab_api.schemas.asset import SignedDownloadOut


class PackageArtifactOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    storage_uri: str
    kind: str | None = None
    content_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    download: SignedDownloadOut


class PackageDetailOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    org_id: uuid.UUID
    status: str
    workflow_key: str
    reel_id: uuid.UUID | None = None
    package_root_uri: str | None = None
    manifest_uri: str | None = None
    manifest_metadata: dict[str, Any] = Field(default_factory=dict)
    manifest_download: SignedDownloadOut | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    provenance_uri: str | None = None
    provenance_download: SignedDownloadOut | None = None
    artifacts: list[PackageArtifactOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
