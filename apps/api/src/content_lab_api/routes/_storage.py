"""Shared storage helpers for URI-based signed download links."""

from __future__ import annotations

from content_lab_api.schemas.asset import SignedDownloadOut
from content_lab_shared.settings import Settings
from content_lab_storage import S3Presigner, S3PresignerConfig


def build_signed_download(*, storage_uri: str, expires_in_seconds: int = 900) -> SignedDownloadOut:
    settings = Settings()
    presigner = S3Presigner(
        S3PresignerConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            expires_in_seconds=expires_in_seconds,
        )
    )
    signed = presigner.presign_download(storage_uri=storage_uri)
    return SignedDownloadOut(
        storage_uri=signed.storage_uri,
        url=signed.url,
        expires_at=signed.expires_at,
    )
