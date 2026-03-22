"""API-key creation and verification helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime

from content_lab_auth.identity import APIKeyRecord, IssuedAPIKey, Role

_KEY_PREFIX_BYTES = 8
_KEY_SECRET_BYTES = 24
_KEY_FORMAT_PREFIX = "clak"


def build_api_key(*, prefix: str | None = None, secret: str | None = None) -> str:
    """Build a plaintext API key using a public prefix and private secret."""
    resolved_prefix = prefix or secrets.token_hex(_KEY_PREFIX_BYTES)
    resolved_secret = secret or secrets.token_urlsafe(_KEY_SECRET_BYTES)
    return f"{_KEY_FORMAT_PREFIX}_{resolved_prefix}_{resolved_secret}"


def extract_key_prefix(plaintext_key: str) -> str:
    """Return the non-secret prefix from a Content Lab API key."""
    parts = plaintext_key.split("_", 2)
    if len(parts) != 3 or parts[0] != _KEY_FORMAT_PREFIX or not parts[1] or not parts[2]:
        raise ValueError("Invalid Content Lab API key format")
    return parts[1]


def hash_api_key(plaintext_key: str, *, salt: str) -> str:
    """Hash API-key material with a per-environment salt for storage."""
    material = f"{salt}:{plaintext_key}".encode()
    return hashlib.sha256(material).hexdigest()


def verify_api_key(plaintext_key: str, *, salt: str, expected_hash: str) -> bool:
    """Compare a plaintext API key against a stored hash in constant time."""
    calculated_hash = hash_api_key(plaintext_key, salt=salt)
    return hmac.compare_digest(calculated_hash, expected_hash)


def issue_api_key(
    *,
    org_id: uuid.UUID,
    role: Role,
    salt: str,
    name: str | None = None,
    expires_at: datetime | None = None,
) -> IssuedAPIKey:
    """Create a new API key and its hashed persistence record."""
    plaintext_key = build_api_key()
    record = APIKeyRecord(
        org_id=org_id,
        role=role,
        key_hash=hash_api_key(plaintext_key, salt=salt),
        key_prefix=extract_key_prefix(plaintext_key),
        name=name,
        api_key_id=uuid.uuid4(),
        expires_at=expires_at,
    )
    return IssuedAPIKey(plaintext_key=plaintext_key, record=record)
