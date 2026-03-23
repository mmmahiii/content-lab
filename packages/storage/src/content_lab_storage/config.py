"""Configuration models shared across S3-compatible storage helpers."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True, slots=True)
class S3StorageConfig:
    """Connection settings for an S3-compatible object store."""

    endpoint: str
    access_key_id: str
    secret_access_key: str
    region: str = "us-east-1"
    service: str = "s3"
    default_bucket: str | None = None

    def normalized_endpoint(self) -> str:
        parsed = urlsplit(self.endpoint)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid storage endpoint: {self.endpoint!r}")
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
