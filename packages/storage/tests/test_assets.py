from __future__ import annotations

import uuid
from unittest.mock import Mock

from content_lab_storage import CanonicalStorageLayout, StoredObject
from content_lab_storage.assets import canonical_asset_filename, persist_asset_bytes
from content_lab_storage.refs import StorageRef


def test_canonical_asset_filename_prefers_explicit_filename() -> None:
    assert (
        canonical_asset_filename("clip", content_type="video/mp4", filename="nested/final-cut.mp4")
        == "final-cut.mp4"
    )


def test_persist_asset_bytes_uses_canonical_derived_path_and_checksum() -> None:
    client = Mock()
    asset_id = uuid.uuid4()
    expected_ref = StorageRef(bucket="content-lab", key=f"assets/derived/{asset_id}/clip.mp4")
    client.put_object.return_value = StoredObject(
        ref=expected_ref,
        size_bytes=11,
        content_type="video/mp4",
        checksum_sha256="sha256:" + ("b" * 64),
    )

    stored = persist_asset_bytes(
        client=client,
        layout=CanonicalStorageLayout(bucket="content-lab"),
        asset_id=asset_id,
        asset_class="clip",
        data=b"video-bytes",
        content_type="video/mp4",
        metadata={"asset-id": str(asset_id)},
    )

    client.put_object.assert_called_once()
    put_kwargs = client.put_object.call_args.kwargs
    assert put_kwargs["ref"].uri == expected_ref.uri
    assert put_kwargs["content_type"] == "video/mp4"
    assert put_kwargs["metadata"] == {"asset-id": str(asset_id)}
    assert put_kwargs["checksum_sha256"] == stored.checksums.content_hash
    assert stored.filename == "clip.mp4"
    assert stored.storage_uri == expected_ref.uri


def test_persist_asset_bytes_handles_duplicate_payloads_with_distinct_asset_paths() -> None:
    client = Mock()
    first_asset_id = uuid.uuid4()
    second_asset_id = uuid.uuid4()

    def _stored(ref: StorageRef) -> StoredObject:
        return StoredObject(ref=ref, checksum_sha256=None)

    client.put_object.side_effect = [
        _stored(StorageRef(bucket="content-lab", key=f"assets/derived/{first_asset_id}/clip.mp4")),
        _stored(StorageRef(bucket="content-lab", key=f"assets/derived/{second_asset_id}/clip.mp4")),
    ]

    first = persist_asset_bytes(
        client=client,
        layout=CanonicalStorageLayout(bucket="content-lab"),
        asset_id=first_asset_id,
        asset_class="clip",
        data=b"same-payload",
        content_type="video/mp4",
    )
    second = persist_asset_bytes(
        client=client,
        layout=CanonicalStorageLayout(bucket="content-lab"),
        asset_id=second_asset_id,
        asset_class="clip",
        data=b"same-payload",
        content_type="video/mp4",
    )

    assert first.checksums.content_hash == second.checksums.content_hash
    assert first.storage_uri != second.storage_uri
