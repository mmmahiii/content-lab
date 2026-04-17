"""Identity and API-key models for Content Lab authentication."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

from pydantic import Field

from content_lab_core.models import DomainModel, _utcnow
from content_lab_shared.settings import Settings

_API_KEY_HASH_VERSION = "v1"
_DEFAULT_API_KEY_PREFIX_LENGTH = 8
_MAX_API_KEY_PREFIX_LENGTH = 16


class APIKeyRecord(DomainModel):
    """Represents a hashed API key issued to a tenant or service account."""

    name: str
    hashed_key: str
    tenant_id: str
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    revoked: bool = False

    def matches(self, raw_key: str, *, salt: str | None = None) -> bool:
        """Return whether ``raw_key`` matches this stored hash."""
        return verify_api_key(raw_key, self.hashed_key, salt=salt)


class Identity(DomainModel):
    """Resolved caller identity attached to each authenticated request."""

    tenant_id: str
    scopes: list[str] = Field(default_factory=list)
    authenticated_at: datetime = Field(default_factory=_utcnow)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def api_key_prefix(raw_key: str, *, prefix_length: int = _DEFAULT_API_KEY_PREFIX_LENGTH) -> str:
    """Return the non-secret prefix operators can use to identify a key."""
    if prefix_length < 1 or prefix_length > _MAX_API_KEY_PREFIX_LENGTH:
        raise ValueError(
            f"prefix_length must be between 1 and {_MAX_API_KEY_PREFIX_LENGTH} characters"
        )
    normalized = _normalize_api_key(raw_key)
    return normalized[:prefix_length]


def hash_api_key(raw_key: str, *, salt: str | None = None) -> str:
    """Hash an API key with a deployment-specific salt for storage at rest."""
    normalized = _normalize_api_key(raw_key)
    salt_value = _resolve_api_key_salt(salt)
    digest = hmac.new(
        salt_value.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{_API_KEY_HASH_VERSION}:{digest}"


def verify_api_key(raw_key: str, stored_hash: str, *, salt: str | None = None) -> bool:
    """Compare a raw API key against a stored hash in constant time."""
    normalized_hash = str(stored_hash).strip()
    if not normalized_hash:
        return False
    if not normalized_hash.startswith(f"{_API_KEY_HASH_VERSION}:"):
        return False
    expected_hash = hash_api_key(raw_key, salt=salt)
    return hmac.compare_digest(normalized_hash, expected_hash)


def _normalize_api_key(raw_key: str) -> str:
    normalized = str(raw_key).strip()
    if not normalized:
        raise ValueError("raw_key must not be blank")
    return normalized


def _resolve_api_key_salt(salt: str | None) -> str:
    if salt is not None:
        normalized = salt.strip()
        if not normalized:
            raise ValueError("salt must not be blank")
        return normalized
    return Settings().api_key_salt.get_secret_value()
