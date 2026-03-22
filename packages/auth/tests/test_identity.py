from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from content_lab_auth import extract_key_prefix, issue_api_key, verify_api_key
from content_lab_auth.identity import APIKeyRecord, Identity


class TestIdentity:
    def test_role_hierarchy(self) -> None:
        ident = Identity(org_id=uuid.uuid4(), role="operator", subject="api_key:test")
        assert ident.has_role("readonly")
        assert ident.has_role("reviewer")
        assert ident.has_role("operator")
        assert not ident.has_role("admin")


class TestAPIKeyRecord:
    def test_expiry_and_revocation_flags(self) -> None:
        rec = APIKeyRecord(
            org_id=uuid.uuid4(),
            role="reviewer",
            key_hash="abc123",
            key_prefix="deadbeef",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),  # noqa: UP017
        )
        assert rec.active
        assert not rec.revoked
        assert not rec.is_expired()


class TestAPIKeyHelpers:
    def test_issue_key_hashes_secret_and_verifies(self) -> None:
        org_id = uuid.uuid4()
        issued = issue_api_key(org_id=org_id, role="admin", salt="test-salt", name="ci")

        assert issued.record.org_id == org_id
        assert issued.record.role == "admin"
        assert issued.record.key_hash != issued.plaintext_key
        assert extract_key_prefix(issued.plaintext_key) == issued.record.key_prefix
        assert verify_api_key(
            issued.plaintext_key,
            salt="test-salt",
            expected_hash=issued.record.key_hash,
        )
