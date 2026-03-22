"""Identity, request-context, and API-key models for Content Lab authentication."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from content_lab_core.models import DomainModel, _utcnow

Role = Literal["owner", "admin", "operator", "reviewer", "readonly"]
AuthScheme = Literal["api_key", "jwt", "oidc"]

_ROLE_RANK: dict[Role, int] = {
    "readonly": 10,
    "reviewer": 20,
    "operator": 30,
    "admin": 40,
    "owner": 50,
}


class APIKeyRecord(DomainModel):
    """Hashed API-key metadata persisted by the API layer."""

    org_id: uuid.UUID
    role: Role
    key_hash: str
    key_prefix: str
    name: str | None = None
    api_key_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def active(self) -> bool:
        return not self.revoked and not self.is_expired()

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        instant = now or _utcnow()
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)  # noqa: UP017
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)  # noqa: UP017
        return expires_at <= instant


class Identity(DomainModel):
    """Resolved caller identity attached to each authenticated request."""

    org_id: uuid.UUID
    role: Role
    auth_scheme: AuthScheme = "api_key"
    subject: str
    api_key_id: uuid.UUID | None = None
    authenticated_at: datetime = Field(default_factory=_utcnow)

    def has_role(self, required_role: Role) -> bool:
        return _ROLE_RANK[self.role] >= _ROLE_RANK[required_role]


class IssuedAPIKey(DomainModel):
    """One-time API-key issuance payload returned only during creation."""

    plaintext_key: str
    record: APIKeyRecord
