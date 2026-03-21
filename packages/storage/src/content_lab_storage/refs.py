"""Storage reference models and helpers for S3/MinIO object addressing."""

from __future__ import annotations

from pydantic import BaseModel


class StorageRef(BaseModel):
    """Immutable reference to an object in S3-compatible storage."""

    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"

    @classmethod
    def from_uri(cls, uri: str) -> StorageRef:
        """Parse an ``s3://bucket/key`` URI into a StorageRef."""
        if not uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI: {uri!r}")
        path = uri[len("s3://") :]
        bucket, _, key = path.partition("/")
        if not bucket or not key:
            raise ValueError(f"Malformed S3 URI (missing bucket or key): {uri!r}")
        return cls(bucket=bucket, key=key)


def build_key(*segments: str) -> str:
    """Join path segments into a normalised storage key (no leading slash)."""
    return "/".join(s.strip("/") for s in segments if s.strip("/"))
