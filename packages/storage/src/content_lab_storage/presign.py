"""Helpers for generating S3-compatible presigned download URLs."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from content_lab_storage.refs import StorageRef

_ALGORITHM = "AWS4-HMAC-SHA256"
_UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _signature_key(*, secret_key: str, datestamp: str, region: str, service: str) -> bytes:
    date_key = _sign(f"AWS4{secret_key}".encode(), datestamp)
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


def _normalize_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid storage endpoint: {endpoint!r}")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _canonical_uri(*, endpoint_path: str, ref: StorageRef) -> str:
    prefix = endpoint_path.rstrip("/")
    key_path = quote(ref.key, safe="/~")
    return f"{prefix}/{ref.bucket}/{key_path}" if prefix else f"/{ref.bucket}/{key_path}"


@dataclass(frozen=True, slots=True)
class S3PresignerConfig:
    """Configuration required to sign S3-compatible URLs."""

    endpoint: str
    access_key_id: str
    secret_access_key: str
    region: str = "us-east-1"
    service: str = "s3"
    expires_in_seconds: int = 900


@dataclass(frozen=True, slots=True)
class PresignedDownload:
    """Generated presigned download metadata."""

    storage_uri: str
    url: str
    expires_at: datetime


class S3Presigner:
    """Generate SigV4 query-authenticated download URLs."""

    def __init__(self, config: S3PresignerConfig) -> None:
        if config.expires_in_seconds <= 0:
            raise ValueError("expires_in_seconds must be positive")
        self._config = config
        self._endpoint = urlsplit(_normalize_endpoint(config.endpoint))

    def presign_download(
        self,
        *,
        storage_uri: str,
        expires_in_seconds: int | None = None,
        issued_at: datetime | None = None,
    ) -> PresignedDownload:
        ref = StorageRef.from_uri(storage_uri)
        ttl_seconds = (
            self._config.expires_in_seconds if expires_in_seconds is None else expires_in_seconds
        )
        if ttl_seconds <= 0:
            raise ValueError("expires_in_seconds must be positive")

        now = (issued_at or datetime.now(UTC)).astimezone(UTC)
        datestamp = now.strftime("%Y%m%d")
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        expires_at = now + timedelta(seconds=ttl_seconds)
        credential_scope = f"{datestamp}/{self._config.region}/{self._config.service}/aws4_request"
        canonical_uri = _canonical_uri(endpoint_path=self._endpoint.path, ref=ref)
        canonical_query_params = {
            "X-Amz-Algorithm": _ALGORITHM,
            "X-Amz-Credential": f"{self._config.access_key_id}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(ttl_seconds),
            "X-Amz-SignedHeaders": "host",
        }
        canonical_query = urlencode(sorted(canonical_query_params.items()))
        canonical_headers = f"host:{self._endpoint.netloc}\n"
        canonical_request = "\n".join(
            [
                "GET",
                canonical_uri,
                canonical_query,
                canonical_headers,
                "host",
                _UNSIGNED_PAYLOAD,
            ]
        )
        canonical_request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = "\n".join(
            [
                _ALGORITHM,
                amz_date,
                credential_scope,
                canonical_request_hash,
            ]
        )
        signing_key = _signature_key(
            secret_key=self._config.secret_access_key,
            datestamp=datestamp,
            region=self._config.region,
            service=self._config.service,
        )
        signature = hmac.new(
            signing_key,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        query_string = urlencode(
            [*sorted(canonical_query_params.items()), ("X-Amz-Signature", signature)]
        )
        url = urlunsplit(
            (
                self._endpoint.scheme,
                self._endpoint.netloc,
                canonical_uri,
                query_string,
                "",
            )
        )
        return PresignedDownload(storage_uri=storage_uri, url=url, expires_at=expires_at)
