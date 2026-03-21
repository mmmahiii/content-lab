"""Identity and API-key models for Content Lab authentication."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from content_lab_core.models import DomainModel, _utcnow


class APIKeyRecord(DomainModel):
    """Represents a hashed API key issued to a tenant or service account."""

    name: str
    hashed_key: str
    tenant_id: str
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    revoked: bool = False


class Identity(DomainModel):
    """Resolved caller identity attached to each authenticated request."""

    tenant_id: str
    scopes: list[str] = Field(default_factory=list)
    authenticated_at: datetime = Field(default_factory=_utcnow)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
