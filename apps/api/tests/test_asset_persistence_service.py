from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from content_lab_api.models import Asset, Org
from content_lab_api.services.asset_persistence import persist_asset_content
from content_lab_storage import StoredObject
from content_lab_storage.refs import StorageRef


class RecordingStorageClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def put_object(
        self,
        *,
        ref: StorageRef,
        data: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        checksum_sha256: str | None = None,
    ) -> StoredObject:
        self.calls.append(
            {
                "ref": ref,
                "data": data,
                "content_type": content_type,
                "metadata": dict(metadata or {}),
                "checksum_sha256": checksum_sha256,
            }
        )
        if self.error is not None:
            raise self.error
        return StoredObject(
            ref=ref,
            size_bytes=len(data),
            content_type=content_type,
            metadata=dict(metadata or {}),
            checksum_sha256=checksum_sha256,
        )


@pytest.fixture
def persisted_org(db_session: Session) -> Generator[uuid.UUID, None, None]:
    org = Org(name="Persistence Org", slug=f"persistence-org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    yield org.id


def _staged_asset(db_session: Session, *, org_id: uuid.UUID) -> Asset:
    asset = Asset(
        org_id=org_id,
        asset_class="clip",
        storage_uri=f"s3://content-lab/assets/raw/{uuid.uuid4()}/source.bin",
        source="runway",
        status="staged",
    )
    db_session.add(asset)
    db_session.flush()
    return asset


def test_persist_asset_content_marks_asset_ready_after_storage_and_metadata_write(
    db_session: Session,
    persisted_org: uuid.UUID,
) -> None:
    asset = _staged_asset(db_session, org_id=persisted_org)
    storage_client = RecordingStorageClient()

    persisted = persist_asset_content(
        db_session,
        asset_id=asset.id,
        data=b"video-bytes",
        content_type="video/mp4",
        width=1080,
        height=1920,
        fps=24,
        duration_seconds=6.0,
        storage_client=storage_client,
    )

    db_session.refresh(asset)
    assert persisted.id == asset.id
    assert asset.status == "ready"
    assert asset.storage_uri == f"s3://content-lab/assets/derived/{asset.id}/clip.mp4"
    assert asset.content_hash == persisted.content_hash
    assert asset.metadata_["width"] == 1080
    assert asset.metadata_["height"] == 1920
    assert asset.metadata_["fps"] == 24
    assert asset.metadata_["duration_seconds"] == 6.0
    assert asset.metadata_["storage"] == {
        "state": "ready",
        "storage_uri": asset.storage_uri,
        "content_hash": asset.content_hash,
        "size_bytes": 11,
        "content_type": "video/mp4",
    }
    assert len(storage_client.calls) == 1
    call = storage_client.calls[0]
    assert call["checksum_sha256"] == asset.content_hash


def test_persist_asset_content_handles_duplicate_content_hashes_predictably(
    db_session: Session,
    persisted_org: uuid.UUID,
) -> None:
    first_asset = _staged_asset(db_session, org_id=persisted_org)
    second_asset = _staged_asset(db_session, org_id=persisted_org)
    storage_client = RecordingStorageClient()

    first_ready = persist_asset_content(
        db_session,
        asset_id=first_asset.id,
        data=b"same-payload",
        content_type="video/mp4",
        storage_client=storage_client,
    )
    second_ready = persist_asset_content(
        db_session,
        asset_id=second_asset.id,
        data=b"same-payload",
        content_type="video/mp4",
        storage_client=storage_client,
    )

    db_session.refresh(first_asset)
    db_session.refresh(second_asset)
    assert first_ready.content_hash == second_ready.content_hash
    assert first_asset.storage_uri != second_asset.storage_uri
    assert first_asset.metadata_["storage"]["storage_uri"] == first_asset.storage_uri
    assert second_asset.metadata_["storage"]["storage_uri"] == second_asset.storage_uri


def test_persist_asset_content_marks_asset_failed_when_storage_write_fails(
    db_session: Session,
    persisted_org: uuid.UUID,
) -> None:
    asset = _staged_asset(db_session, org_id=persisted_org)
    staged_uri = asset.storage_uri
    storage_client = RecordingStorageClient(error=RuntimeError("minio unavailable"))

    with pytest.raises(RuntimeError, match="minio unavailable"):
        persist_asset_content(
            db_session,
            asset_id=asset.id,
            data=b"video-bytes",
            content_type="video/mp4",
            fps=24,
            storage_client=storage_client,
        )

    db_session.refresh(asset)
    assert asset.status == "failed"
    assert asset.storage_uri == staged_uri
    assert asset.content_hash is None
    assert asset.metadata_["fps"] == 24
    assert asset.metadata_["storage"]["state"] == "failed"
    assert asset.metadata_["storage"]["storage_uri"] == staged_uri
    assert asset.metadata_["storage"]["failure"] == {
        "stage": "storage_write",
        "message": "minio unavailable",
        "error_type": "RuntimeError",
    }


def test_persist_asset_content_marks_asset_failed_when_db_finalization_fails(
    db_session: Session,
    persisted_org: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _staged_asset(db_session, org_id=persisted_org)
    db_session.commit()
    asset = db_session.get(Asset, asset.id)
    assert asset is not None
    storage_client = RecordingStorageClient()
    real_commit = db_session.commit
    commit_calls = {"count": 0}

    def flaky_commit() -> None:
        commit_calls["count"] += 1
        if commit_calls["count"] == 1:
            raise RuntimeError("db finalization failed")
        real_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)

    with pytest.raises(RuntimeError, match="db finalization failed"):
        persist_asset_content(
            db_session,
            asset_id=asset.id,
            data=b"video-bytes",
            content_type="video/mp4",
            storage_client=storage_client,
        )

    db_session.refresh(asset)
    assert asset.status == "failed"
    assert asset.storage_uri == f"s3://content-lab/assets/derived/{asset.id}/clip.mp4"
    assert asset.metadata_["storage"]["state"] == "failed"
    assert asset.metadata_["storage"]["storage_uri"] == asset.storage_uri
    assert asset.metadata_["storage"]["failure"] == {
        "stage": "metadata_persistence",
        "message": "db finalization failed",
        "error_type": "RuntimeError",
    }
