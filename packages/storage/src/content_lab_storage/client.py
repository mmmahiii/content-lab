"""Canonical S3-compatible storage client for Content Lab."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

import boto3
from botocore.config import Config

from content_lab_storage.checksums import normalize_sha256
from content_lab_storage.config import S3StorageConfig
from content_lab_storage.presign import PresignedDownload, S3Presigner, S3PresignerConfig
from content_lab_storage.refs import StorageRef, build_key

_CHECKSUM_METADATA_KEY = "checksum-sha256"


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Metadata returned by storage operations."""

    ref: StorageRef
    size_bytes: int | None = None
    etag: str | None = None
    content_type: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    last_modified: datetime | None = None
    checksum_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievedObject(StoredObject):
    """Object download result."""

    body: bytes = b""


class S3StorageClient:
    """Thin, S3-compatible wrapper used by API and worker services."""

    def __init__(self, config: S3StorageConfig) -> None:
        self._config = config
        self._client = boto3.session.Session().client(
            "s3",
            endpoint_url=config.normalized_endpoint(),
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            region_name=config.region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self._presigner = S3Presigner(
            S3PresignerConfig(
                endpoint=config.endpoint,
                access_key_id=config.access_key_id,
                secret_access_key=config.secret_access_key,
                region=config.region,
                service=config.service,
            )
        )

    def build_ref(self, key: str, *, bucket: str | None = None) -> StorageRef:
        """Build a ref from a key plus either an explicit or default bucket."""

        normalized_key = build_key(key)
        if not normalized_key:
            raise ValueError("key must not be empty")
        return StorageRef(bucket=self._resolve_bucket(bucket), key=normalized_key)

    def put_object(
        self,
        *,
        data: bytes,
        ref: StorageRef | None = None,
        storage_uri: str | None = None,
        key: str | None = None,
        bucket: str | None = None,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
        checksum_sha256: str | None = None,
    ) -> StoredObject:
        resolved_ref = self._resolve_ref(ref=ref, storage_uri=storage_uri, key=key, bucket=bucket)
        object_metadata = dict(metadata or {})
        if checksum_sha256 is not None:
            object_metadata[_CHECKSUM_METADATA_KEY] = normalize_sha256(checksum_sha256)

        put_kwargs: dict[str, Any] = {
            "Bucket": resolved_ref.bucket,
            "Key": resolved_ref.key,
            "Body": data,
        }
        if content_type is not None:
            put_kwargs["ContentType"] = content_type
        if object_metadata:
            put_kwargs["Metadata"] = object_metadata

        self._client.put_object(**put_kwargs)
        return self.head_object(ref=resolved_ref)

    def get_object(
        self,
        *,
        ref: StorageRef | None = None,
        storage_uri: str | None = None,
        key: str | None = None,
        bucket: str | None = None,
    ) -> RetrievedObject:
        resolved_ref = self._resolve_ref(ref=ref, storage_uri=storage_uri, key=key, bucket=bucket)
        response = self._client.get_object(Bucket=resolved_ref.bucket, Key=resolved_ref.key)
        body = cast(Any, response["Body"]).read()
        stored = self._stored_object_from_response(ref=resolved_ref, response=response)
        return RetrievedObject(
            ref=stored.ref,
            size_bytes=stored.size_bytes,
            etag=stored.etag,
            content_type=stored.content_type,
            metadata=stored.metadata,
            last_modified=stored.last_modified,
            checksum_sha256=stored.checksum_sha256,
            body=body,
        )

    def head_object(
        self,
        *,
        ref: StorageRef | None = None,
        storage_uri: str | None = None,
        key: str | None = None,
        bucket: str | None = None,
    ) -> StoredObject:
        resolved_ref = self._resolve_ref(ref=ref, storage_uri=storage_uri, key=key, bucket=bucket)
        response = self._client.head_object(Bucket=resolved_ref.bucket, Key=resolved_ref.key)
        return self._stored_object_from_response(ref=resolved_ref, response=response)

    def list_objects(
        self,
        *,
        prefix: str | None = None,
        bucket: str | None = None,
        ref: StorageRef | None = None,
        storage_uri: str | None = None,
        max_keys: int | None = None,
    ) -> list[StoredObject]:
        if ref is not None or storage_uri is not None:
            prefix_ref = self._resolve_ref(ref=ref, storage_uri=storage_uri)
            bucket_name = prefix_ref.bucket
            key_prefix = prefix_ref.key
        else:
            bucket_name = self._resolve_bucket(bucket)
            key_prefix = build_key(prefix or "")

        paginator = self._client.get_paginator("list_objects_v2")
        paginate_kwargs: dict[str, Any] = {"Bucket": bucket_name, "Prefix": key_prefix}
        if max_keys is not None:
            paginate_kwargs["PaginationConfig"] = {"MaxItems": max_keys, "PageSize": max_keys}

        objects: list[StoredObject] = []
        for page in paginator.paginate(**paginate_kwargs):
            for item in cast(list[dict[str, Any]], page.get("Contents", [])):
                objects.append(
                    StoredObject(
                        ref=StorageRef(bucket=bucket_name, key=str(item["Key"])),
                        size_bytes=int(item.get("Size", 0)),
                        etag=_clean_etag(item.get("ETag")),
                        last_modified=cast(datetime | None, item.get("LastModified")),
                    )
                )
        return objects

    def presign_download(
        self,
        *,
        ref: StorageRef | None = None,
        storage_uri: str | None = None,
        key: str | None = None,
        bucket: str | None = None,
        expires_in_seconds: int | None = None,
        issued_at: datetime | None = None,
    ) -> PresignedDownload:
        resolved_ref = self._resolve_ref(ref=ref, storage_uri=storage_uri, key=key, bucket=bucket)
        return self._presigner.presign_download(
            storage_uri=resolved_ref.uri,
            expires_in_seconds=expires_in_seconds,
            issued_at=issued_at,
        )

    def _resolve_ref(
        self,
        *,
        ref: StorageRef | None = None,
        storage_uri: str | None = None,
        key: str | None = None,
        bucket: str | None = None,
    ) -> StorageRef:
        provided = sum(value is not None for value in (ref, storage_uri, key))
        if provided != 1:
            raise ValueError("provide exactly one of ref, storage_uri, or key")
        if ref is not None:
            return ref
        if storage_uri is not None:
            return StorageRef.from_uri(storage_uri)
        return self.build_ref(cast(str, key), bucket=bucket)

    def _resolve_bucket(self, bucket: str | None) -> str:
        resolved_bucket = bucket or self._config.default_bucket
        if resolved_bucket is None or not resolved_bucket.strip():
            raise ValueError("bucket is required when no default_bucket is configured")
        return resolved_bucket

    @staticmethod
    def _stored_object_from_response(
        *, ref: StorageRef, response: Mapping[str, Any]
    ) -> StoredObject:
        metadata = dict(cast(dict[str, str], response.get("Metadata", {})))
        return StoredObject(
            ref=ref,
            size_bytes=_coerce_int(response.get("ContentLength")),
            etag=_clean_etag(response.get("ETag")),
            content_type=cast(str | None, response.get("ContentType")),
            metadata=metadata,
            last_modified=cast(datetime | None, response.get("LastModified")),
            checksum_sha256=metadata.get(_CHECKSUM_METADATA_KEY),
        )


def _clean_etag(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip('"')


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
