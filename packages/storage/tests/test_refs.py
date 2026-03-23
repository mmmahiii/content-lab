from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from content_lab_storage import S3Presigner, S3PresignerConfig
from content_lab_storage.refs import StorageRef, build_key


class TestStorageRef:
    def test_uri_property(self) -> None:
        ref = StorageRef(bucket="content-lab", key="assets/img.png")
        assert ref.uri == "s3://content-lab/assets/img.png"

    def test_from_uri(self) -> None:
        ref = StorageRef.from_uri("s3://my-bucket/path/to/file.mp4")
        assert ref.bucket == "my-bucket"
        assert ref.key == "path/to/file.mp4"

    def test_roundtrip(self) -> None:
        original = StorageRef(bucket="b", key="k/v.txt")
        restored = StorageRef.from_uri(original.uri)
        assert restored == original

    def test_invalid_scheme(self) -> None:
        with pytest.raises(ValueError, match="Invalid S3 URI"):
            StorageRef.from_uri("gs://bucket/key")

    def test_missing_key(self) -> None:
        with pytest.raises(ValueError, match="Malformed"):
            StorageRef.from_uri("s3://bucket/")


class TestBuildKey:
    def test_basic(self) -> None:
        assert build_key("packages", "abc123", "reel.mp4") == "packages/abc123/reel.mp4"

    def test_strips_slashes(self) -> None:
        assert build_key("/a/", "/b/", "/c") == "a/b/c"

    def test_empty_segments(self) -> None:
        assert build_key("a", "", "b") == "a/b"


class TestS3Presigner:
    def test_presign_download_uses_canonical_storage_uri(self) -> None:
        presigner = S3Presigner(
            S3PresignerConfig(
                endpoint="http://localhost:9000",
                access_key_id="minioadmin",
                secret_access_key="minioadmin",
                expires_in_seconds=600,
            )
        )

        signed = presigner.presign_download(
            storage_uri="s3://content-lab/reels/packages/reel-123/final_video.mp4",
            issued_at=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        )

        parsed = urlsplit(signed.url)
        params = parse_qs(parsed.query)
        assert parsed.scheme == "http"
        assert parsed.netloc == "localhost:9000"
        assert parsed.path == "/content-lab/reels/packages/reel-123/final_video.mp4"
        assert params["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
        assert params["X-Amz-Credential"] == ["minioadmin/20260323/us-east-1/s3/aws4_request"]
        assert params["X-Amz-Date"] == ["20260323T120000Z"]
        assert params["X-Amz-Expires"] == ["600"]
        assert params["X-Amz-SignedHeaders"] == ["host"]
        assert len(params["X-Amz-Signature"][0]) == 64
        assert signed.expires_at == datetime(2026, 3, 23, 12, 10, tzinfo=UTC)

    def test_presign_download_rejects_invalid_ttl(self) -> None:
        presigner = S3Presigner(
            S3PresignerConfig(
                endpoint="http://localhost:9000",
                access_key_id="minioadmin",
                secret_access_key="minioadmin",
            )
        )

        with pytest.raises(ValueError, match="positive"):
            presigner.presign_download(
                storage_uri="s3://content-lab/assets/example.png", expires_in_seconds=0
            )
