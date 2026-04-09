from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

from content_lab_assets.providers.runway import (
    RunwayDownloadedAsset,
    RunwayInsufficientCreditsError,
    RunwaySubmittedTask,
    RunwayTaskSnapshot,
)
from content_lab_assets.store import ProviderJobSnapshot, StoredRunwayGeneration
from content_lab_storage import StorageRef, StoredObject
from content_lab_worker.actors.runway import (
    RetryableRunwayActorError,
    TerminalRunwayActorError,
    process_runway_asset,
    reconcile_runway_asset,
)


class FakeRunwayStore:
    def __init__(self, state: StoredRunwayGeneration) -> None:
        self.state = state

    def load_generation(self, *, asset_id: uuid.UUID | str) -> StoredRunwayGeneration:
        assert str(self.state.asset_id) == str(asset_id)
        return self.state

    def mark_running(
        self,
        generation: StoredRunwayGeneration,
        *,
        external_ref: str | None,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
    ) -> StoredRunwayGeneration:
        self.state = replace(
            generation,
            task_status="running",
            task_result=None if task_result is None else dict(task_result),
            provider_job=self._provider_job(
                generation, external_ref, provider_status, provider_metadata
            ),
        )
        return self.state

    def mark_retryable(
        self,
        generation: StoredRunwayGeneration,
        *,
        reason: str,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
        external_ref: str | None = None,
    ) -> StoredRunwayGeneration:
        result = {
            "reason": reason,
            "retryable": True,
            **({} if task_result is None else dict(task_result)),
        }
        self.state = replace(
            generation,
            task_status="retrying",
            task_result=result,
            provider_job=self._provider_job(
                generation, external_ref, provider_status, provider_metadata
            ),
        )
        return self.state

    def mark_failed(
        self,
        generation: StoredRunwayGeneration,
        *,
        reason: str,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
        asset_metadata: Mapping[str, Any] | None = None,
        external_ref: str | None = None,
    ) -> StoredRunwayGeneration:
        result = {
            "reason": reason,
            "retryable": False,
            **({} if task_result is None else dict(task_result)),
        }
        self.state = replace(
            generation,
            asset_status="failed",
            asset_metadata=_merge_dicts(generation.asset_metadata, asset_metadata),
            task_status="failed",
            task_result=result,
            provider_job=self._provider_job(
                generation, external_ref, provider_status, provider_metadata
            ),
        )
        return self.state

    def mark_ready(
        self,
        generation: StoredRunwayGeneration,
        *,
        storage_uri: str,
        content_hash: str,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
        asset_metadata: Mapping[str, Any] | None = None,
        external_ref: str | None = None,
    ) -> StoredRunwayGeneration:
        metadata = _merge_dicts(generation.asset_metadata, asset_metadata)
        metadata["content_hash"] = content_hash
        self.state = replace(
            generation,
            asset_status="ready",
            storage_uri=storage_uri,
            asset_metadata=metadata,
            task_status="succeeded",
            task_result=None if task_result is None else dict(task_result),
            provider_job=self._provider_job(
                generation, external_ref, provider_status, provider_metadata
            ),
        )
        return self.state

    @staticmethod
    def _provider_job(
        generation: StoredRunwayGeneration,
        external_ref: str | None,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None,
    ) -> ProviderJobSnapshot | None:
        if external_ref is None:
            return generation.provider_job
        return ProviderJobSnapshot(
            id=uuid.uuid4(),
            org_id=generation.org_id,
            provider="runway",
            external_ref=external_ref,
            task_id=generation.task_id,
            status=provider_status,
            metadata={} if provider_metadata is None else dict(provider_metadata),
        )


class FakeRunwayClient:
    def __init__(
        self,
        *,
        submit_id: str = "rwy-task-123",
        snapshots: list[RunwayTaskSnapshot],
        downloaded_asset: RunwayDownloadedAsset | None = None,
    ) -> None:
        self.submit_id = submit_id
        self.snapshots = list(snapshots)
        self.downloaded_asset = downloaded_asset
        self.submit_calls = 0
        self.polled_refs: list[str] = []

    def submit_generation(
        self,
        *,
        task_payload: Mapping[str, Any],
        canonical_params: Mapping[str, Any],
        idempotency_key: str,
    ) -> RunwaySubmittedTask:
        self.submit_calls += 1
        assert task_payload["provider_submission"]["provider"] == "runway"
        assert canonical_params["model"] == "gen4.5"
        assert idempotency_key.startswith("asset.generate:")
        return RunwaySubmittedTask(id=self.submit_id, raw_response={"id": self.submit_id})

    def get_task(self, external_ref: str) -> RunwayTaskSnapshot:
        self.polled_refs.append(external_ref)
        return self.snapshots.pop(0)

    def download_output(self, task: RunwayTaskSnapshot) -> RunwayDownloadedAsset:
        assert task.is_success
        if self.downloaded_asset is None:
            raise AssertionError("download_output was not configured")
        return self.downloaded_asset


class FakeStorageClient:
    def __init__(self) -> None:
        self.objects: list[StoredObject] = []

    def put_object(
        self,
        *,
        data: bytes,
        key: str,
        content_type: str | None = None,
        checksum_sha256: str | None = None,
    ) -> StoredObject:
        stored = StoredObject(
            ref=StorageRef(bucket="content-lab", key=key),
            size_bytes=len(data),
            content_type=content_type,
            checksum_sha256=checksum_sha256,
        )
        self.objects.append(stored)
        return stored


def test_process_runway_asset_moves_staged_asset_to_ready() -> None:
    generation = _base_generation()
    store = FakeRunwayStore(generation)
    client = FakeRunwayClient(
        snapshots=[
            RunwayTaskSnapshot(id="rwy-task-123", status="RUNNING"),
            RunwayTaskSnapshot(
                id="rwy-task-123",
                status="SUCCEEDED",
                output=("https://cdn.runwayml.com/out/generated.mp4",),
            ),
        ],
        downloaded_asset=RunwayDownloadedAsset(
            url="https://cdn.runwayml.com/out/generated.mp4",
            body=b"video-bytes",
            content_type="video/mp4",
        ),
    )
    storage = FakeStorageClient()

    result = process_runway_asset(
        asset_id=generation.asset_id,
        store=store,
        provider_client=client,
        storage_client=storage,
        max_polls=3,
        poll_interval_seconds=0,
    )

    assert result["status"] == "ready"
    assert result["provider_job"]["external_ref"] == "rwy-task-123"
    assert result["storage_uri"] == (
        f"s3://content-lab/assets/derived/{generation.asset_id}/source.mp4"
    )
    assert store.state.asset_status == "ready"
    assert store.state.task_status == "succeeded"
    assert store.state.provider_job is not None
    assert store.state.provider_job.status == "succeeded"
    assert store.state.provider_job.external_ref == "rwy-task-123"
    assert client.submit_calls == 1
    assert client.polled_refs == ["rwy-task-123", "rwy-task-123"]
    assert len(storage.objects) == 1
    assert storage.objects[0].checksum_sha256 is not None


def test_process_runway_asset_fails_terminal_when_runway_returns_insufficient_credits() -> None:
    generation = _base_generation()

    class CreditsExhaustedClient:
        def submit_generation(
            self,
            *,
            task_payload: Mapping[str, Any],
            canonical_params: Mapping[str, Any],
            idempotency_key: str,
        ) -> RunwaySubmittedTask:
            raise RunwayInsufficientCreditsError(
                'Runway API HTTP 400 on POST /v1/text_to_video: {"error":"no credits"}'
            )

        def get_task(self, external_ref: str) -> RunwayTaskSnapshot:
            raise AssertionError("poll should not run")

        def download_output(self, task: RunwayTaskSnapshot) -> RunwayDownloadedAsset:
            raise AssertionError("download should not run")

    store = FakeRunwayStore(generation)
    with pytest.raises(TerminalRunwayActorError, match="insufficient credits"):
        process_runway_asset(
            asset_id=generation.asset_id,
            store=store,
            provider_client=CreditsExhaustedClient(),
            storage_client=FakeStorageClient(),
            max_polls=1,
            poll_interval_seconds=0,
        )
    assert store.state.asset_status == "failed"
    assert store.state.task_status == "failed"
    assert store.state.task_result is not None
    assert store.state.task_result.get("retryable") is False
    assert store.state.task_result.get("phase") == "submit"


def test_process_runway_asset_submits_when_provider_job_only_has_registry_external_ref() -> None:
    """API-created provider_jobs rows use runway-gen45:… keys; Runway GET /v1/tasks expects a UUID."""
    generation = _base_generation()
    generation = replace(
        generation,
        provider_job=ProviderJobSnapshot(
            id=uuid.uuid4(),
            org_id=generation.org_id,
            provider="runway",
            external_ref="runway-gen45:" + "ab" * 32,
            task_id=generation.task_id,
            status="submitted",
            metadata={},
        ),
    )
    store = FakeRunwayStore(generation)
    client = FakeRunwayClient(
        snapshots=[
            RunwayTaskSnapshot(id="rwy-task-123", status="RUNNING"),
            RunwayTaskSnapshot(
                id="rwy-task-123",
                status="SUCCEEDED",
                output=("https://cdn.runwayml.com/out/generated.mp4",),
            ),
        ],
        downloaded_asset=RunwayDownloadedAsset(
            url="https://cdn.runwayml.com/out/generated.mp4",
            body=b"video-bytes",
            content_type="video/mp4",
        ),
    )
    result = process_runway_asset(
        asset_id=generation.asset_id,
        store=store,
        provider_client=client,
        storage_client=FakeStorageClient(),
        max_polls=3,
        poll_interval_seconds=0,
    )
    assert result["status"] == "ready"
    assert client.submit_calls == 1
    assert client.polled_refs == ["rwy-task-123", "rwy-task-123"]


def test_process_runway_asset_marks_retryable_failure_without_resubmitting_existing_job() -> None:
    generation = _base_generation()
    generation = replace(
        generation,
        provider_job=ProviderJobSnapshot(
            id=uuid.uuid4(),
            org_id=generation.org_id,
            provider="runway",
            external_ref="existing-job",
            task_id=generation.task_id,
            status="running",
            metadata={},
        ),
    )
    store = FakeRunwayStore(generation)
    client = FakeRunwayClient(
        snapshots=[
            RunwayTaskSnapshot(
                id="existing-job",
                status="FAILED",
                failure_code="INTERNAL.BAD_OUTPUT",
            )
        ],
    )

    with pytest.raises(RetryableRunwayActorError):
        process_runway_asset(
            asset_id=generation.asset_id,
            store=store,
            provider_client=client,
            storage_client=FakeStorageClient(),
            max_polls=1,
            poll_interval_seconds=0,
        )

    assert client.submit_calls == 0
    assert store.state.asset_status == "staged"
    assert store.state.task_status == "retrying"
    assert store.state.provider_job is not None
    assert store.state.provider_job.status == "retryable"
    assert store.state.task_result is not None
    assert store.state.task_result["retryable"] is True
    assert store.state.task_result["failure_code"] == "INTERNAL.BAD_OUTPUT"


def test_process_runway_asset_marks_terminal_failure_and_fails_asset() -> None:
    generation = _base_generation()
    store = FakeRunwayStore(generation)
    client = FakeRunwayClient(
        snapshots=[
            RunwayTaskSnapshot(
                id="rwy-task-999",
                status="FAILED",
                failure_code="SAFETY.TEXT",
            )
        ],
    )

    with pytest.raises(TerminalRunwayActorError):
        process_runway_asset(
            asset_id=generation.asset_id,
            store=store,
            provider_client=client,
            storage_client=FakeStorageClient(),
            max_polls=1,
            poll_interval_seconds=0,
        )

    assert store.state.asset_status == "failed"
    assert store.state.task_status == "failed"
    assert store.state.provider_job is not None
    assert store.state.provider_job.status == "failed"
    assert store.state.task_result is not None
    assert store.state.task_result["retryable"] is False
    assert store.state.task_result["failure_code"] == "SAFETY.TEXT"


def test_reconcile_runway_asset_skips_duplicate_finalization_for_ready_assets() -> None:
    generation = replace(
        _base_generation(),
        asset_status="ready",
        task_status="succeeded",
        provider_job=ProviderJobSnapshot(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            provider="runway",
            external_ref="existing-job",
            task_id=uuid.uuid4(),
            status="running",
            metadata={},
        ),
    )
    store = FakeRunwayStore(generation)
    client = FakeRunwayClient(snapshots=[])

    result = reconcile_runway_asset(
        asset_id=generation.asset_id,
        external_ref="existing-job",
        store=store,
        provider_client=client,
        storage_client=FakeStorageClient(),
    )

    assert result["status"] == "ready"
    assert result["already_finalized"] is True
    assert result["reconciliation_status"] == "already_finalized"
    assert client.polled_refs == []


def _base_generation(
    provider_job: ProviderJobSnapshot | None = None,
) -> StoredRunwayGeneration:
    asset_id = uuid.uuid4()
    task_id = uuid.uuid4()
    org_id = uuid.uuid4()
    return StoredRunwayGeneration(
        asset_id=asset_id,
        org_id=org_id,
        asset_class="clip",
        asset_status="staged",
        asset_source="runway",
        storage_uri=f"s3://content-lab/assets/raw/{asset_id}/source.bin",
        asset_key='{"provider":"runway"}',
        asset_key_hash="abc123" * 10 + "abcd",
        asset_metadata={"intent": {"request_id": "req-1"}},
        canonical_params={
            "provider": "runway",
            "model": "gen4.5",
            "prompt": "Hero launch shot",
            "ratio": "9:16",
            "duration_seconds": 6,
        },
        task_id=task_id,
        task_type="asset.generate",
        task_status="queued",
        task_idempotency_key=("asset.generate:" + ("abc123" * 10 + "abcd")),
        task_payload={
            "canonical_params": {
                "provider": "runway",
                "model": "gen4.5",
                "prompt": "Hero launch shot",
            },
            "provider_submission": {
                "provider": "runway",
                "model": "gen4.5",
                "asset_class": "clip",
            },
            "request": {"prompt": "Hero launch shot"},
        },
        task_result=None,
        provider_job=provider_job,
    )


def _merge_dicts(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(left or {})
    if right is not None:
        merged.update(dict(right))
    return merged
