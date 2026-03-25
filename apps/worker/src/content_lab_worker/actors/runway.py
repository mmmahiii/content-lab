"""Runway worker actor for staged generated-asset finalization."""

from __future__ import annotations

import mimetypes
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

import dramatiq

from content_lab_assets.providers.runway import (
    HTTPRunwayClient,
    RunwayClient,
    RunwayDownloadedAsset,
    RunwayFailureDisposition,
    RunwayTaskSnapshot,
    classify_failure,
)
from content_lab_assets.store import RunwayAssetStore, SQLRunwayAssetStore, StoredRunwayGeneration
from content_lab_shared.settings import Settings
from content_lab_storage import (
    CanonicalStorageLayout,
    S3StorageClient,
    S3StorageConfig,
    StoredObject,
    checksum_bytes,
)
from content_lab_worker.actors._shared import ActorLike, build_queue_name, get_actor_logger

logger = get_actor_logger("runway")
QUEUE_NAME = build_queue_name("runway")
_DEFAULT_MAX_POLLS = 3
_DEFAULT_POLL_INTERVAL_SECONDS = 5.0


class RetryableRunwayActorError(RuntimeError):
    """Raised when the provider or download path should be retried later."""


class TerminalRunwayActorError(RuntimeError):
    """Raised when the provider returned a terminal failure."""


class StorageClientLike(Protocol):
    """Minimal storage client surface used by the actor."""

    def put_object(
        self,
        *,
        data: bytes,
        key: str,
        content_type: str | None = None,
        checksum_sha256: str | None = None,
    ) -> StoredObject: ...


def process_runway_asset(
    *,
    asset_id: uuid.UUID | str,
    store: RunwayAssetStore | None = None,
    provider_client: RunwayClient | None = None,
    storage_client: StorageClientLike | None = None,
    settings: Settings | None = None,
    max_polls: int = _DEFAULT_MAX_POLLS,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Advance a staged generated asset through provider completion and finalization."""

    resolved_settings = settings or Settings()
    resolved_store = store or SQLRunwayAssetStore(settings=resolved_settings)
    resolved_provider = provider_client or HTTPRunwayClient.from_settings(resolved_settings)
    resolved_storage = storage_client or _build_storage_client(resolved_settings)
    generation = resolved_store.load_generation(asset_id=asset_id)

    if generation.is_ready:
        return _existing_summary(generation)
    if generation.is_terminal_failure:
        return _terminal_summary(generation)
    if generation.task_id is None or generation.task_idempotency_key is None:
        raise LookupError(f"Asset {generation.asset_id} is missing its asset.generate task")

    external_ref = _existing_external_ref(generation)
    if external_ref is None:
        try:
            submitted = resolved_provider.submit_generation(
                task_payload=generation.task_payload,
                canonical_params=generation.canonical_params,
                idempotency_key=generation.task_idempotency_key,
            )
        except Exception as exc:
            resolved_store.mark_retryable(
                generation,
                reason="provider submission failed",
                provider_status="submission_failed",
                task_result={"error": str(exc), "phase": "submit"},
            )
            raise RetryableRunwayActorError(str(exc)) from exc

        external_ref = submitted.id
        generation = resolved_store.mark_running(
            generation,
            external_ref=external_ref,
            provider_status="submitted",
            provider_metadata=submitted.metadata(),
            task_result={
                "asset_id": str(generation.asset_id),
                "phase": "submitted",
                "provider": "runway",
                "provider_job_id": external_ref,
            },
        )

    snapshot = _poll_for_terminal_state(
        generation=generation,
        external_ref=external_ref,
        store=resolved_store,
        provider_client=resolved_provider,
        max_polls=max_polls,
        poll_interval_seconds=poll_interval_seconds,
    )

    if snapshot.is_success:
        return _finalize_success(
            generation=generation,
            snapshot=snapshot,
            external_ref=external_ref,
            store=resolved_store,
            provider_client=resolved_provider,
            storage_client=resolved_storage,
            settings=resolved_settings,
        )

    if snapshot.is_failure:
        return _handle_failed_task(
            generation=generation,
            snapshot=snapshot,
            external_ref=external_ref,
            store=resolved_store,
        )

    resolved_store.mark_retryable(
        generation,
        reason="provider task did not reach a terminal state within the poll budget",
        provider_status=snapshot.normalized_status.lower(),
        provider_metadata=snapshot.metadata(),
        task_result={
            "asset_id": str(generation.asset_id),
            "phase": "poll",
            "provider": "runway",
            "provider_job_id": external_ref,
            "provider_task_status": snapshot.normalized_status.lower(),
        },
        external_ref=external_ref,
    )
    raise RetryableRunwayActorError(
        f"Runway task {external_ref} is still {snapshot.normalized_status.lower()}"
    )


def reconcile_runway_asset(
    *,
    asset_id: uuid.UUID | str,
    external_ref: str | None = None,
    store: RunwayAssetStore | None = None,
    provider_client: RunwayClient | None = None,
    storage_client: StorageClientLike | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Re-poll an existing Runway job without re-submitting provider work."""

    resolved_settings = settings or Settings()
    resolved_store = store or SQLRunwayAssetStore(settings=resolved_settings)
    resolved_provider = provider_client or HTTPRunwayClient.from_settings(resolved_settings)
    resolved_storage = storage_client or _build_storage_client(resolved_settings)
    generation = resolved_store.load_generation(asset_id=asset_id)

    if generation.is_ready:
        return {
            **_existing_summary(generation),
            "already_finalized": True,
            "provider_job_status": "succeeded",
            "reconciliation_status": "already_finalized",
        }
    if generation.is_terminal_failure:
        return {
            **_terminal_summary(generation),
            "already_finalized": True,
            "provider_job_status": "failed",
            "reconciliation_status": "already_finalized",
        }

    resolved_external_ref = external_ref or _existing_external_ref(generation)
    if resolved_external_ref is None:
        raise LookupError(f"Asset {generation.asset_id} is missing a persisted provider job")

    snapshot = _poll_for_terminal_state(
        generation=generation,
        external_ref=resolved_external_ref,
        store=resolved_store,
        provider_client=resolved_provider,
        max_polls=1,
        poll_interval_seconds=0,
    )

    if snapshot.is_success:
        result = _finalize_success(
            generation=generation,
            snapshot=snapshot,
            external_ref=resolved_external_ref,
            store=resolved_store,
            provider_client=resolved_provider,
            storage_client=resolved_storage,
            settings=resolved_settings,
        )
        result["reconciliation_status"] = "repaired"
        return result

    if snapshot.is_failure:
        return _handle_failed_task(
            generation=generation,
            snapshot=snapshot,
            external_ref=resolved_external_ref,
            store=resolved_store,
        )

    resolved_store.mark_retryable(
        generation,
        reason="provider job remained non-terminal during sweeper reconciliation",
        provider_status=snapshot.normalized_status.lower(),
        provider_metadata=snapshot.metadata(),
        task_result={
            "asset_id": str(generation.asset_id),
            "phase": "reconcile",
            "provider": "runway",
            "provider_job_id": resolved_external_ref,
            "provider_task_status": snapshot.normalized_status.lower(),
        },
        external_ref=resolved_external_ref,
    )
    raise RetryableRunwayActorError(
        f"Runway task {resolved_external_ref} is still {snapshot.normalized_status.lower()}"
    )


def _finalize_success(
    *,
    generation: StoredRunwayGeneration,
    snapshot: RunwayTaskSnapshot,
    external_ref: str,
    store: RunwayAssetStore,
    provider_client: RunwayClient,
    storage_client: StorageClientLike,
    settings: Settings,
) -> dict[str, Any]:
    try:
        downloaded = provider_client.download_output(snapshot)
        store_download = _persist_download(
            generation=generation,
            downloaded=downloaded,
            storage_client=storage_client,
            settings=settings,
        )
    except RetryableRunwayActorError:
        raise
    except Exception as exc:
        store.mark_retryable(
            generation,
            reason="downloading or storing the provider output failed",
            provider_status="succeeded",
            provider_metadata=snapshot.metadata(),
            task_result={
                "asset_id": str(generation.asset_id),
                "error": str(exc),
                "phase": "download",
                "provider": "runway",
                "provider_job_id": external_ref,
            },
            external_ref=external_ref,
        )
        raise RetryableRunwayActorError(str(exc)) from exc

    download_metadata = {
        "content_type": downloaded.content_type,
        "filename": downloaded.filename,
        "size_bytes": len(downloaded.body),
        "source_url": downloaded.url,
        "storage_uri": store_download["storage_uri"],
    }

    ready_summary = {
        "asset_id": str(generation.asset_id),
        "canonical_params": dict(generation.canonical_params),
        "content_hash": store_download["content_hash"],
        "download": download_metadata,
        "phase": "ready",
        "provider": "runway",
        "provider_job": {
            "external_ref": external_ref,
            "status": "succeeded",
        },
        "provenance": {
            "asset_key_hash": generation.asset_key_hash,
            "task_id": None if generation.task_id is None else str(generation.task_id),
            "task_idempotency_key": generation.task_idempotency_key,
        },
        "status": "ready",
        "storage_uri": store_download["storage_uri"],
        "task_id": None if generation.task_id is None else str(generation.task_id),
    }

    asset_metadata = {
        "download": download_metadata,
        "runway": {
            "external_ref": external_ref,
            "status": "succeeded",
        },
    }
    provider_metadata = snapshot.metadata()
    provider_metadata["download"] = dict(download_metadata)

    store.mark_ready(
        generation,
        storage_uri=store_download["storage_uri"],
        content_hash=store_download["content_hash"],
        provider_status="succeeded",
        provider_metadata=provider_metadata,
        task_result=ready_summary,
        asset_metadata=asset_metadata,
        external_ref=external_ref,
    )
    return ready_summary


def _persist_download(
    *,
    generation: StoredRunwayGeneration,
    downloaded: RunwayDownloadedAsset,
    storage_client: StorageClientLike,
    settings: Settings,
) -> dict[str, str]:
    checksums = checksum_bytes(downloaded.body)
    layout = CanonicalStorageLayout(bucket=settings.minio_bucket)
    extension = _resolve_extension(downloaded)
    target_key = layout.derived_asset_object(generation.asset_id, f"source{extension}").key
    stored_object = storage_client.put_object(
        data=downloaded.body,
        key=target_key,
        content_type=downloaded.content_type or _content_type_for_extension(extension),
        checksum_sha256=checksums.content_hash,
    )
    return {
        "content_hash": checksums.content_hash,
        "storage_uri": stored_object.ref.uri,
    }


def _handle_failed_task(
    *,
    generation: StoredRunwayGeneration,
    snapshot: RunwayTaskSnapshot,
    external_ref: str,
    store: RunwayAssetStore,
) -> dict[str, Any]:
    failure_disposition = classify_failure(snapshot.failure_code)
    summary = {
        "asset_id": str(generation.asset_id),
        "failure_code": snapshot.failure_code,
        "phase": "provider_failed",
        "provider": "runway",
        "provider_job": {
            "external_ref": external_ref,
            "status": snapshot.normalized_status.lower(),
        },
        "provider_task_status": snapshot.normalized_status.lower(),
        "retryable": failure_disposition == RunwayFailureDisposition.RETRYABLE,
        "status": "failed"
        if failure_disposition == RunwayFailureDisposition.TERMINAL
        else "retrying",
        "task_id": None if generation.task_id is None else str(generation.task_id),
    }
    if snapshot.failure_code is not None:
        summary["failure_code"] = snapshot.failure_code

    if failure_disposition == RunwayFailureDisposition.RETRYABLE:
        store.mark_retryable(
            generation,
            reason="provider task failed with a retryable failure code",
            provider_status="retryable",
            provider_metadata=snapshot.metadata(),
            task_result=summary,
            external_ref=external_ref,
        )
        raise RetryableRunwayActorError(
            f"Runway task {external_ref} failed with retryable code {snapshot.failure_code!r}"
        )

    store.mark_failed(
        generation,
        reason="provider task failed with a terminal failure code",
        provider_status="failed",
        provider_metadata=snapshot.metadata(),
        task_result=summary,
        asset_metadata={
            "runway": {
                "external_ref": external_ref,
                "failure_code": snapshot.failure_code,
                "status": "failed",
            }
        },
        external_ref=external_ref,
    )
    raise TerminalRunwayActorError(
        f"Runway task {external_ref} failed with terminal code {snapshot.failure_code!r}"
    )


def _poll_for_terminal_state(
    *,
    generation: StoredRunwayGeneration,
    external_ref: str,
    store: RunwayAssetStore,
    provider_client: RunwayClient,
    max_polls: int,
    poll_interval_seconds: float,
) -> RunwayTaskSnapshot:
    last_snapshot: RunwayTaskSnapshot | None = None
    for attempt in range(max_polls):
        try:
            snapshot = provider_client.get_task(external_ref)
        except Exception as exc:
            store.mark_retryable(
                generation,
                reason="provider polling failed",
                provider_status="polling_failed",
                task_result={
                    "asset_id": str(generation.asset_id),
                    "error": str(exc),
                    "phase": "poll",
                    "provider": "runway",
                    "provider_job_id": external_ref,
                },
                external_ref=external_ref,
            )
            raise RetryableRunwayActorError(str(exc)) from exc

        last_snapshot = snapshot
        if snapshot.is_success or snapshot.is_failure:
            return snapshot

        store.mark_running(
            generation,
            external_ref=external_ref,
            provider_status=snapshot.normalized_status.lower(),
            provider_metadata=snapshot.metadata(),
            task_result={
                "asset_id": str(generation.asset_id),
                "phase": "poll",
                "provider": "runway",
                "provider_job_id": external_ref,
                "provider_task_status": snapshot.normalized_status.lower(),
                "poll_attempt": attempt + 1,
            },
        )
        if attempt + 1 < max_polls and poll_interval_seconds > 0:
            time.sleep(poll_interval_seconds)

    if last_snapshot is None:
        raise RetryableRunwayActorError(f"Runway task {external_ref} could not be polled")
    return last_snapshot


def _existing_external_ref(generation: StoredRunwayGeneration) -> str | None:
    if generation.provider_job is not None:
        return str(generation.provider_job.external_ref)
    runway_state = generation.asset_metadata.get("runway")
    if isinstance(runway_state, Mapping):
        external_ref = runway_state.get("external_ref")
        if external_ref is not None and str(external_ref).strip():
            return str(external_ref).strip()
    return None


def _existing_summary(generation: StoredRunwayGeneration) -> dict[str, Any]:
    return {
        "asset_id": str(generation.asset_id),
        "status": "ready",
        "storage_uri": generation.storage_uri,
        "task_id": None if generation.task_id is None else str(generation.task_id),
    }


def _terminal_summary(generation: StoredRunwayGeneration) -> dict[str, Any]:
    return {
        "asset_id": str(generation.asset_id),
        "status": "failed",
        "task_id": None if generation.task_id is None else str(generation.task_id),
    }


def _resolve_extension(downloaded: RunwayDownloadedAsset) -> str:
    extension = Path(downloaded.filename).suffix.lower()
    if extension:
        return extension
    guessed = mimetypes.guess_extension(downloaded.content_type or "", strict=False)
    if guessed is not None:
        return guessed
    return ".bin"


def _content_type_for_extension(extension: str) -> str | None:
    return mimetypes.guess_type(f"asset{extension}", strict=False)[0]


def _build_storage_client(settings: Settings) -> S3StorageClient:
    return S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )


@dramatiq.actor(queue_name=QUEUE_NAME)
def finalize_runway_asset(asset_id: str) -> dict[str, Any]:
    logger.info("processing staged Runway asset %s", asset_id)
    return process_runway_asset(asset_id=asset_id)


ACTORS: tuple[ActorLike, ...] = (finalize_runway_asset,)

__all__ = [
    "ACTORS",
    "QUEUE_NAME",
    "RetryableRunwayActorError",
    "TerminalRunwayActorError",
    "finalize_runway_asset",
    "process_runway_asset",
    "reconcile_runway_asset",
]
