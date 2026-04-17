from __future__ import annotations

import pytest

from content_lab_auth.identity import (
    APIKeyRecord,
    Identity,
    api_key_prefix,
    hash_api_key,
    verify_api_key,
)


class TestIdentity:
    def test_defaults(self) -> None:
        ident = Identity(tenant_id="t-1", scopes=["read", "write"])
        assert ident.tenant_id == "t-1"
        assert ident.has_scope("read")
        assert not ident.has_scope("admin")

    def test_empty_scopes(self) -> None:
        ident = Identity(tenant_id="t-2")
        assert ident.scopes == []
        assert not ident.has_scope("read")


class TestAPIKeyRecord:
    def test_creation(self) -> None:
        rec = APIKeyRecord(
            name="ci-key",
            hashed_key="abc123",
            tenant_id="t-1",
            scopes=["read"],
        )
        assert rec.name == "ci-key"
        assert rec.tenant_id == "t-1"
        assert not rec.revoked
        assert rec.expires_at is None

    def test_matches_uses_constant_hash_verification(self) -> None:
        hashed = hash_api_key("live-secret-key", salt="salt-one")
        rec = APIKeyRecord(name="ci-key", hashed_key=hashed, tenant_id="t-1")

        assert rec.matches("live-secret-key", salt="salt-one")
        assert not rec.matches("wrong-key", salt="salt-one")


class TestAPIKeyHashing:
    def test_hash_api_key_is_stable_for_same_salt(self) -> None:
        assert hash_api_key("live-secret-key", salt="salt-one") == hash_api_key(
            "live-secret-key",
            salt="salt-one",
        )

    def test_hash_api_key_changes_with_salt(self) -> None:
        first = hash_api_key("live-secret-key", salt="salt-one")
        second = hash_api_key("live-secret-key", salt="salt-two")

        assert first != second
        assert "live-secret-key" not in first

    def test_verify_api_key_rejects_unknown_hash_version(self) -> None:
        assert not verify_api_key("live-secret-key", "legacy:abc123", salt="salt-one")

    def test_api_key_prefix_returns_safe_identifier_slice(self) -> None:
        assert api_key_prefix("  live-secret-key  ", prefix_length=4) == "live"

    def test_api_key_prefix_rejects_invalid_lengths(self) -> None:
        with pytest.raises(ValueError, match="prefix_length"):
            api_key_prefix("live-secret-key", prefix_length=0)
