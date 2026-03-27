"""Object-storage integrity verification helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from botocore.exceptions import ClientError

from content_lab_storage.checksums import checksum_bytes, normalize_sha256
from content_lab_storage.client import S3StorageClient


@dataclass(frozen=True, slots=True)
class ObjectIntegrityResult:
    """Stable outcome for a single object integrity probe."""

    storage_uri: str
    status: str
    exists: bool
    expected_checksum_sha256: str | None = None
    actual_checksum_sha256: str | None = None
    size_bytes: int | None = None
    detail: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def checksum_verified(self) -> bool:
        return self.actual_checksum_sha256 is not None

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "storage_uri": self.storage_uri,
            "status": self.status,
            "exists": self.exists,
            "checksum_verified": self.checksum_verified,
        }
        if self.expected_checksum_sha256 is not None:
            payload["expected_checksum_sha256"] = self.expected_checksum_sha256
        if self.actual_checksum_sha256 is not None:
            payload["actual_checksum_sha256"] = self.actual_checksum_sha256
        if self.size_bytes is not None:
            payload["size_bytes"] = self.size_bytes
        if self.detail is not None:
            payload["detail"] = self.detail
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


class ObjectIntegrityVerifier(Protocol):
    """Boundary used by orchestrator reconciliation flows."""

    def verify_object(
        self,
        *,
        storage_uri: str,
        expected_checksum_sha256: str | None = None,
        verify_checksum: bool = False,
    ) -> ObjectIntegrityResult: ...


class S3ObjectIntegrityVerifier:
    """Verify object existence and, when requested, recompute checksums."""

    def __init__(self, client: S3StorageClient) -> None:
        self._client = client

    def verify_object(
        self,
        *,
        storage_uri: str,
        expected_checksum_sha256: str | None = None,
        verify_checksum: bool = False,
    ) -> ObjectIntegrityResult:
        normalized_expected, expected_error = _normalize_optional_sha256(expected_checksum_sha256)
        if expected_error is not None:
            return ObjectIntegrityResult(
                storage_uri=storage_uri,
                status="corrupt",
                exists=False,
                detail=expected_error,
            )

        try:
            stored = self._client.head_object(storage_uri=storage_uri)
        except ValueError:
            return ObjectIntegrityResult(
                storage_uri=storage_uri,
                status="skipped",
                exists=False,
                expected_checksum_sha256=normalized_expected,
                detail="storage URI is not an s3:// object reference",
            )
        except ClientError as exc:
            if _is_missing_storage_error(exc):
                return ObjectIntegrityResult(
                    storage_uri=storage_uri,
                    status="missing",
                    exists=False,
                    expected_checksum_sha256=normalized_expected,
                    detail="object does not exist in storage",
                )
            raise

        metadata = dict(stored.metadata)
        normalized_metadata_checksum, metadata_error = _normalize_optional_sha256(
            stored.checksum_sha256
        )
        if metadata_error is not None and normalized_expected is None:
            return ObjectIntegrityResult(
                storage_uri=storage_uri,
                status="corrupt",
                exists=True,
                expected_checksum_sha256=normalized_expected,
                size_bytes=stored.size_bytes,
                detail=metadata_error,
                metadata=metadata,
            )

        should_verify_checksum = (
            verify_checksum
            or normalized_expected is not None
            or normalized_metadata_checksum is not None
        )
        if not should_verify_checksum:
            return ObjectIntegrityResult(
                storage_uri=storage_uri,
                status="healthy",
                exists=True,
                expected_checksum_sha256=normalized_expected,
                size_bytes=stored.size_bytes,
                metadata=metadata,
            )

        try:
            retrieved = self._client.get_object(storage_uri=storage_uri)
        except ClientError as exc:
            if _is_missing_storage_error(exc):
                return ObjectIntegrityResult(
                    storage_uri=storage_uri,
                    status="missing",
                    exists=False,
                    expected_checksum_sha256=normalized_expected,
                    detail="object disappeared during checksum verification",
                    metadata=metadata,
                )
            raise

        actual_checksum = checksum_bytes(retrieved.body).content_hash
        comparison_checksum = normalized_expected or normalized_metadata_checksum
        if comparison_checksum is not None and actual_checksum != comparison_checksum:
            return ObjectIntegrityResult(
                storage_uri=storage_uri,
                status="corrupt",
                exists=True,
                expected_checksum_sha256=comparison_checksum,
                actual_checksum_sha256=actual_checksum,
                size_bytes=retrieved.size_bytes,
                detail="object checksum does not match the persisted checksum",
                metadata=dict(retrieved.metadata),
            )

        return ObjectIntegrityResult(
            storage_uri=storage_uri,
            status="healthy",
            exists=True,
            expected_checksum_sha256=normalized_expected or normalized_metadata_checksum,
            actual_checksum_sha256=actual_checksum,
            size_bytes=retrieved.size_bytes,
            metadata=dict(retrieved.metadata),
        )


def _normalize_optional_sha256(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    try:
        return normalize_sha256(value), None
    except ValueError:
        return None, "checksum metadata is not a valid sha256 digest"


def _is_missing_storage_error(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", "")).strip()
    return code in {"404", "NoSuchKey", "NotFound"}


__all__ = [
    "ObjectIntegrityResult",
    "ObjectIntegrityVerifier",
    "S3ObjectIntegrityVerifier",
]
