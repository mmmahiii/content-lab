from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import Mock

import pytest

from content_lab_storage import S3StorageClient, S3StorageConfig


def _build_client() -> S3StorageClient:
    return S3StorageClient(
        S3StorageConfig(
            endpoint="http://localhost:9000",
            access_key_id="minioadmin",
            secret_access_key="minioadmin",
            default_bucket="content-lab",
        )
    )


def test_put_object_uses_default_bucket_and_persists_checksum_metadata() -> None:
    client = _build_client()
    mocked = Mock()
    mocked.head_object.return_value = {
        "ContentLength": 11,
        "ContentType": "text/plain",
        "ETag": '"etag-123"',
        "LastModified": datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        "Metadata": {"checksum-sha256": "sha256:" + ("a" * 64), "source": "pytest"},
    }
    client._client = mocked

    stored = client.put_object(
        key="assets/raw/asset-123/original.txt",
        data=b"hello world",
        content_type="text/plain",
        metadata={"source": "pytest"},
        checksum_sha256="A" * 64,
    )

    mocked.put_object.assert_called_once()
    put_kwargs = mocked.put_object.call_args.kwargs
    assert put_kwargs["Bucket"] == "content-lab"
    assert put_kwargs["Key"] == "assets/raw/asset-123/original.txt"
    assert put_kwargs["Body"] == b"hello world"
    assert put_kwargs["ContentType"] == "text/plain"
    assert put_kwargs["Metadata"] == {
        "source": "pytest",
        "checksum-sha256": "sha256:" + ("a" * 64),
    }
    assert stored.checksum_sha256 == "sha256:" + ("a" * 64)
    assert stored.etag == "etag-123"


def test_get_object_returns_payload_and_metadata() -> None:
    client = _build_client()
    mocked = Mock()
    mocked.get_object.return_value = {
        "Body": BytesIO(b"video-bytes"),
        "ContentLength": 11,
        "ContentType": "video/mp4",
        "ETag": '"etag-456"',
        "LastModified": datetime(2026, 3, 23, 12, 5, tzinfo=UTC),
        "Metadata": {"checksum-sha256": "sha256:" + ("b" * 64)},
    }
    client._client = mocked

    fetched = client.get_object(storage_uri="s3://content-lab/assets/derived/clip-123/clip.mp4")

    mocked.get_object.assert_called_once_with(
        Bucket="content-lab",
        Key="assets/derived/clip-123/clip.mp4",
    )
    assert fetched.body == b"video-bytes"
    assert fetched.content_type == "video/mp4"
    assert fetched.checksum_sha256 == "sha256:" + ("b" * 64)
    assert fetched.etag == "etag-456"


def test_list_objects_uses_prefix_and_returns_refs() -> None:
    client = _build_client()
    mocked = Mock()
    paginator = Mock()
    paginator.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "reels/packages/reel-123/final_video.mp4",
                    "Size": 42,
                    "ETag": '"etag-789"',
                    "LastModified": datetime(2026, 3, 23, 12, 10, tzinfo=UTC),
                }
            ]
        }
    ]
    mocked.get_paginator.return_value = paginator
    client._client = mocked

    objects = client.list_objects(prefix="reels/packages/reel-123")

    mocked.get_paginator.assert_called_once_with("list_objects_v2")
    paginator.paginate.assert_called_once_with(
        Bucket="content-lab", Prefix="reels/packages/reel-123"
    )
    assert [item.ref.uri for item in objects] == [
        "s3://content-lab/reels/packages/reel-123/final_video.mp4"
    ]
    assert objects[0].etag == "etag-789"
    assert objects[0].size_bytes == 42


def test_build_ref_requires_a_bucket_when_no_default_exists() -> None:
    client = S3StorageClient(
        S3StorageConfig(
            endpoint="http://localhost:9000",
            access_key_id="minioadmin",
            secret_access_key="minioadmin",
        )
    )

    with pytest.raises(ValueError, match="bucket is required"):
        client.build_ref("assets/raw/a/original.bin")
