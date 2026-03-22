from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from content_lab_api.deps.auth import (
    APIKeyLookup,
    AuditSink,
    CreatedAPIKeyResponse,
    get_api_key_store,
    get_audit_sink,
)
from content_lab_api.deps.database import get_db
from content_lab_api.main import app
from content_lab_auth import APIKeyRecord, Identity, issue_api_key


class RecordingAPIKeyStore(APIKeyLookup):
    def __init__(self) -> None:
        self.records: dict[str, APIKeyRecord] = {}

    def get_by_prefix(self, prefix: str) -> APIKeyRecord | None:
        return self.records.get(prefix)

    def create(
        self,
        *,
        org_id: uuid.UUID,
        role: str,
        name: str | None,
        expires_at: datetime | None,
    ) -> tuple[str, APIKeyRecord]:
        issued = issue_api_key(
            org_id=org_id,
            role=role,
            salt="test-salt",
            name=name,
            expires_at=expires_at,
        )
        self.records[issued.record.key_prefix] = issued.record
        return issued.plaintext_key, issued.record


class RecordingAuditSink(AuditSink):
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def write(
        self,
        *,
        org_id: uuid.UUID,
        action: str,
        resource_type: str,
        actor_type: str | None,
        actor_id: str | None,
        resource_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        self.events.append(
            {
                "org_id": org_id,
                "action": action,
                "resource_type": resource_type,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "resource_id": resource_id,
                "payload": payload,
            }
        )


class DummySession:
    def __init__(self) -> None:
        self.committed = False

    def commit(self) -> None:
        self.committed = True


@pytest.fixture
def route_harness(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, RecordingAPIKeyStore, RecordingAuditSink, DummySession]:
    monkeypatch.setenv("API_KEY_SALT", "test-salt")
    store = RecordingAPIKeyStore()
    audit = RecordingAuditSink()
    db = DummySession()
    app.dependency_overrides[get_api_key_store] = lambda: store
    app.dependency_overrides[get_audit_sink] = lambda: audit
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    yield client, store, audit, db
    app.dependency_overrides.clear()


@pytest.fixture
def admin_identity() -> Identity:
    return Identity(org_id=uuid.uuid4(), role="admin", subject="api_key:test-admin")


@pytest.fixture
def readonly_identity() -> Identity:
    return Identity(org_id=uuid.uuid4(), role="readonly", subject="api_key:test-readonly")


def test_create_api_key_returns_plaintext_once_and_audits(
    route_harness: tuple[TestClient, RecordingAPIKeyStore, RecordingAuditSink, DummySession],
    admin_identity: Identity,
) -> None:
    client, store, audit, db = route_harness
    from content_lab_api.deps import get_request_identity

    app.dependency_overrides[get_request_identity] = lambda: admin_identity

    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)  # noqa: UP017
    response = client.post(
        "/auth/api-keys",
        json={"name": "ops automation", "role": "operator", "expires_at": expires_at.isoformat()},
    )

    assert response.status_code == 201
    payload = CreatedAPIKeyResponse.model_validate(response.json())
    assert payload.api_key.startswith("clak_")
    assert payload.org_id == admin_identity.org_id
    assert payload.role == "operator"
    assert payload.name == "ops automation"
    assert payload.api_key not in {record.key_hash for record in store.records.values()}
    assert db.committed is True
    assert len(audit.events) == 1
    assert audit.events[0]["action"] == "api_key.created"
    assert audit.events[0]["payload"]["key_prefix"] == payload.key_prefix


@pytest.mark.parametrize(
    ("path", "identity", "expected_status"),
    [
        ("/auth/guards/admin", "admin", 200),
        ("/auth/guards/admin", "operator", 403),
        ("/auth/guards/operator", "operator", 200),
        ("/auth/guards/operator", "reviewer", 403),
        ("/auth/guards/reviewer", "reviewer", 200),
        ("/auth/guards/reviewer", "readonly", 403),
        ("/auth/guards/readonly", "readonly", 200),
    ],
)
def test_role_guards_enforce_hierarchy(
    route_harness: tuple[TestClient, RecordingAPIKeyStore, RecordingAuditSink, DummySession],
    admin_identity: Identity,
    path: str,
    identity: str,
    expected_status: int,
) -> None:
    client, _, _, _ = route_harness
    from content_lab_api.deps import get_request_identity

    current_identity = admin_identity.model_copy(update={"role": identity})
    app.dependency_overrides[get_request_identity] = lambda: current_identity

    response = client.get(path)

    assert response.status_code == expected_status


def test_mutating_route_emits_audit_event(
    route_harness: tuple[TestClient, RecordingAPIKeyStore, RecordingAuditSink, DummySession],
    admin_identity: Identity,
) -> None:
    client, _, audit, _ = route_harness
    from content_lab_api.deps import get_request_identity

    operator_identity = admin_identity.model_copy(update={"role": "operator"})
    app.dependency_overrides[get_request_identity] = lambda: operator_identity

    response = client.post("/auth/mutations/echo", json={"resource_id": "reel-123", "note": "approved"})

    assert response.status_code == 200
    assert audit.events[-1]["action"] == "demo.mutation"
    assert audit.events[-1]["resource_id"] == "reel-123"
    assert audit.events[-1]["actor_id"] == operator_identity.subject
