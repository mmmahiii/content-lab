from __future__ import annotations

import os
import uuid
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from content_lab_storage import (
    CanonicalStorageLayout,
    S3StorageClient,
    S3StorageConfig,
    checksum_bytes,
)


def _integration_client() -> tuple[S3StorageClient, str]:
    bucket = os.getenv("MINIO_BUCKET", "content-lab")
    client = S3StorageClient(
        S3StorageConfig(
            endpoint=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
            access_key_id=os.getenv("MINIO_ROOT_USER", "minioadmin"),
            secret_access_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
            default_bucket=bucket,
        )
    )
    return client, bucket


def _require_minio() -> None:
    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000").rstrip("/")
    try:
        with urlopen(f"{endpoint}/minio/health/live", timeout=2) as response:
            if response.status != 200:
                pytest.skip("MinIO endpoint is not healthy")
    except (TimeoutError, URLError, OSError):
        pytest.skip("MinIO endpoint is not available for the integration smoke test")


@pytest.mark.integration
def test_s3_storage_client_smoke_against_local_minio() -> None:
    _require_minio()
    client, bucket = _integration_client()
    layout = CanonicalStorageLayout(bucket=bucket)
    reel_id = uuid.uuid4()
    package = layout.reel_package(reel_id)
    payload = b'{"version":1,"artifact_count":2}'
    checksums = checksum_bytes(payload)

    stored = client.put_object(
        ref=package.manifest,
        data=payload,
        content_type="application/json",
        metadata={"source": "pytest"},
        checksum_sha256=checksums.content_hash,
    )

    assert stored.ref == package.manifest
    assert stored.size_bytes == len(payload)
    assert stored.checksum_sha256 == checksums.content_hash

    headed = client.head_object(ref=package.manifest)
    assert headed.content_type == "application/json"
    assert headed.metadata["source"] == "pytest"

    fetched = client.get_object(ref=package.manifest)
    assert fetched.body == payload
    assert fetched.checksum_sha256 == checksums.content_hash

    listed = client.list_objects(ref=package.root)
    assert package.manifest.uri in {item.ref.uri for item in listed}

    signed = client.presign_download(ref=package.manifest, expires_in_seconds=300)
    with urlopen(signed.url, timeout=5) as response:
        assert response.status == 200
        assert response.read() == payload
