from __future__ import annotations

import base64
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import Asset, Org
from content_lab_storage.assets import StoredAssetBytes
from content_lab_storage.checksums import checksum_bytes
from content_lab_storage.client import S3StorageClient, StoredObject
from content_lab_storage.paths import CanonicalStorageLayout
from content_lab_storage.refs import StorageRef


def _fake_persist_source(
    *,
    client: S3StorageClient,
    layout: CanonicalStorageLayout,
    asset_id: uuid.UUID | str,
    asset_class: str,
    data: bytes,
    content_type: str | None,
    metadata: dict[str, str] | None = None,
    filename: str | None = None,
) -> StoredAssetBytes:
    del client, layout, metadata, asset_id, asset_class
    fname = filename or "asset.png"
    sums = checksum_bytes(data)
    ref = StorageRef(bucket="test-bucket", key=f"raw/{sums.content_hash[:8]}/{fname}")
    stored = StoredObject(
        ref=ref,
        size_bytes=len(data),
        content_type=content_type,
        checksum_sha256=sums.content_hash,
    )
    return StoredAssetBytes(stored_object=stored, checksums=sums, filename=str(fname))


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mP8z8AARQAFAAIB"
    "AaxooGQAAAAASUVORK5CYII="
)


@pytest.fixture
def assets_client(db_session: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def org_id(db_session: Session) -> uuid.UUID:
    org = Org(name="Import Org", slug=f"import-org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return org.id


def test_import_approved_external_persists_registry_asset(
    assets_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    with (
        patch(
            "content_lab_api.services.asset_packs._download_approved_external_url",
            return_value=(_PNG, "image/png"),
        ),
        patch(
            "content_lab_api.services.asset_packs.persist_source_asset_bytes",
            side_effect=_fake_persist_source,
        ),
    ):
        response = assets_client.post(
            f"/orgs/{org_id}/assets/import-approved-external",
            json={
                "asset_kind": "object_image",
                "external_source_url": "https://cdn.example.com/approved/still.png",
                "usage_rights_confirmed": True,
                "filename": "still.png",
                "source_metadata": {
                    "source_type": "approved_external_source",
                    "source_provider": "Example CDN",
                    "external_source_url": "https://cdn.example.com/approved/still.png",
                    "usage_allowed": True,
                    "commercial_use_allowed": False,
                    "licence_type": "custom",
                    "licence_notes": "Operator approved for internal reels",
                },
            },
        )
    assert response.status_code == 201
    payload = response.json()
    assert payload["licence_metadata_complete"] is True
    assert payload["reused_existing_asset"] is False
    aid = uuid.UUID(payload["asset_id"])
    row = db_session.get(Asset, aid)
    assert row is not None
    assert row.status == "ready"
    assert row.source == "imported"
    assert row.metadata_["source_metadata"]["source_provider"] == "Example CDN"
    assert row.metadata_.get("import_flags") is None


def test_import_rejects_blocked_url(
    assets_client: TestClient,
    org_id: uuid.UUID,
) -> None:
    response = assets_client.post(
        f"/orgs/{org_id}/assets/import-approved-external",
        json={
            "asset_kind": "object_image",
            "external_source_url": "http://localhost/stolen.png",
            "usage_rights_confirmed": True,
            "source_metadata": {
                "source_type": "approved_external_source",
                "source_provider": "Bad Local Source",
                "usage_allowed": True,
                "licence_type": "x",
            },
        },
    )
    assert response.status_code == 422


def test_import_requires_source_provider_metadata(
    assets_client: TestClient,
    org_id: uuid.UUID,
) -> None:
    response = assets_client.post(
        f"/orgs/{org_id}/assets/import-approved-external",
        json={
            "asset_kind": "object_image",
            "external_source_url": "https://cdn.example.com/approved/still.png",
            "usage_rights_confirmed": True,
            "source_metadata": {
                "source_type": "approved_external_source",
                "usage_allowed": True,
                "licence_type": "custom",
            },
        },
    )
    assert response.status_code == 422
    assert "source_metadata.source_provider" in response.text
