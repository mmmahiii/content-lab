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


class PackageOutboxNotificationOut(BaseModel):
    """Delivery state for the terminal process_reel package-ready outbox event."""

    model_config = ConfigDict(extra="forbid")

    event_type: str | None = None
    delivery_status: str | None = None
    attempt_count: int | None = None
    dispatched_at: datetime | None = None
    is_pending: bool = False
    is_failed: bool = False
    message: str | None = None


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
    outbox_notification: PackageOutboxNotificationOut | None = None
    created_at: datetime
    updated_at: datetime
