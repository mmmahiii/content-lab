from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from content_lab_api.deps.auth import APIKeyLookup, get_api_key_store
from content_lab_api.main import app
from content_lab_auth import APIKeyRecord, issue_api_key


class StubAPIKeyStore(APIKeyLookup):
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
        raise NotImplementedError


@pytest.fixture
def key_store(monkeypatch: pytest.MonkeyPatch) -> StubAPIKeyStore:
    monkeypatch.setenv("API_KEY_SALT", "test-salt")
    store = StubAPIKeyStore()
    app.dependency_overrides[get_api_key_store] = lambda: store
    yield store
    app.dependency_overrides.clear()


@pytest.fixture
def client(key_store: StubAPIKeyStore) -> TestClient:
    return TestClient(app)


def _store_key(
    store: StubAPIKeyStore,
    *,
    role: str = "admin",
    expires_at: datetime | None = None,
    revoked: bool = False,
) -> str:
    issued = issue_api_key(
        org_id=uuid.uuid4(),
        role=role,
        salt="test-salt",
        name="fixture-key",
        expires_at=expires_at,
    )
    record = issued.record.model_copy(
        update={"revoked_at": datetime.now(timezone.utc) if revoked else None}  # noqa: UP017
    )
    store.records[record.key_prefix] = record
    return issued.plaintext_key


def test_missing_api_key_returns_401(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API key"


def test_revoked_api_key_returns_401(client: TestClient, key_store: StubAPIKeyStore) -> None:
    api_key = _store_key(key_store, revoked=True)

    response = client.get("/auth/me", headers={"X-API-Key": api_key})

    assert response.status_code == 401
    assert response.json()["detail"] == "API key has been revoked"


def test_expired_api_key_returns_401(client: TestClient, key_store: StubAPIKeyStore) -> None:
    api_key = _store_key(key_store, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))  # noqa: UP017

    response = client.get("/auth/me", headers={"X-API-Key": api_key})

    assert response.status_code == 401
    assert response.json()["detail"] == "API key has expired"


def test_valid_api_key_resolves_org_scoped_identity(
    client: TestClient, key_store: StubAPIKeyStore
) -> None:
    org_id = uuid.uuid4()
    issued = issue_api_key(org_id=org_id, role="reviewer", salt="test-salt", name="review-key")
    key_store.records[issued.record.key_prefix] = issued.record

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {issued.plaintext_key}"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["org_id"] == str(org_id)
    assert payload["role"] == "reviewer"
    assert payload["subject"].startswith("api_key:")
