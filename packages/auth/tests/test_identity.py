from __future__ import annotations

from content_lab_auth.identity import APIKeyRecord, Identity


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
