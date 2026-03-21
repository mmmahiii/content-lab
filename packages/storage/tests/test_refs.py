from __future__ import annotations

import pytest

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
