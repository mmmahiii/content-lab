"""Provider-facing worker actor definitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from content_lab_assets.providers.runway.jobs import (
    RUNWAY_PROVIDER,
    RunwayJobStatus,
    normalize_runway_job_status,
)
from content_lab_runs import TaskRowSpec, TaskStatus, build_task_idempotency_key
from content_lab_worker.actors._shared import ActorLike, build_queue_name, get_actor_logger

logger = get_actor_logger("provider")
QUEUE_NAME = build_queue_name("provider")
_PROVIDER_SUBMISSION_TASK_TYPE = "provider.submit"
_RUNWAY_SWEEP_THRESHOLDS = {
    RunwayJobStatus.SUBMITTED.value: timedelta(minutes=15),
    RunwayJobStatus.RUNNING.value: timedelta(minutes=30),
    "polling_failed": timedelta(minutes=10),
    "retryable": timedelta(minutes=10),
    "submission_failed": timedelta(minutes=10),
}
_TERMINAL_PROVIDER_JOB_STATUSES = frozenset(
    {
        RunwayJobStatus.SUCCEEDED.value,
        RunwayJobStatus.FAILED.value,
        RunwayJobStatus.CANCELLED.value,
    }
)


@dataclass(frozen=True, slots=True)
class ProviderSweepThreshold:
    """Sweep threshold attached to a provider-job status."""

    provider: str
    status: str
    max_age: timedelta


def is_terminal_provider_job_status(*, provider: str, status: str) -> bool:
    """Return whether a provider-job status should be excluded from sweeping."""

    normalized_provider = provider.strip().lower()
    normalized_status = status.strip().lower()
    if normalized_provider == RUNWAY_PROVIDER:
        return normalized_status in _TERMINAL_PROVIDER_JOB_STATUSES
    return normalized_status in {"succeeded", "failed", "cancelled"}


def get_provider_sweep_threshold(
    *,
    provider: str,
    status: str,
) -> ProviderSweepThreshold | None:
    """Return the stale-age threshold for a non-terminal provider-job status."""

    normalized_provider = provider.strip().lower()
    normalized_status = status.strip().lower()
    if is_terminal_provider_job_status(provider=normalized_provider, status=normalized_status):
        return None
    if normalized_provider == RUNWAY_PROVIDER:
        max_age = _RUNWAY_SWEEP_THRESHOLDS.get(normalized_status, timedelta(minutes=30))
        return ProviderSweepThreshold(
            provider=normalized_provider,
            status=normalized_status,
            max_age=max_age,
        )
    return ProviderSweepThreshold(
        provider=normalized_provider,
        status=normalized_status,
        max_age=timedelta(minutes=30),
    )


def build_provider_submission_task(
    *,
    org_id: str,
    provider: str,
    external_ref: str,
    run_id: str | None = None,
    asset_id: str | None = None,
    provider_job_id: str | None = None,
    provider_job_status: str = RunwayJobStatus.SUBMITTED.value,
    payload: dict[str, Any] | None = None,
) -> TaskRowSpec:
    """Build a durable task envelope for a provider submission/polling cycle."""

    normalized_provider = provider.strip().lower()
    normalized_external_ref = external_ref.strip()
    if not normalized_provider:
        raise ValueError("provider must not be blank")
    if not normalized_external_ref:
        raise ValueError("external_ref must not be blank")
    normalized_provider_job_status = (
        normalize_runway_job_status(provider_job_status).value
        if normalized_provider == RUNWAY_PROVIDER
        else provider_job_status.strip().lower()
    )
    if not normalized_provider_job_status:
        raise ValueError("provider_job_status must not be blank")
    task_payload = {
        "provider": normalized_provider,
        "external_ref": normalized_external_ref,
        "provider_job_status": normalized_provider_job_status,
        **({} if payload is None else dict(payload)),
    }
    if asset_id is not None:
        task_payload["asset_id"] = asset_id
    if provider_job_id is not None:
        task_payload["provider_job_id"] = provider_job_id
    return TaskRowSpec(
        org_id=org_id,
        task_type=_PROVIDER_SUBMISSION_TASK_TYPE,
        idempotency_key=build_task_idempotency_key(
            _PROVIDER_SUBMISSION_TASK_TYPE,
            payload={
                "provider": normalized_provider,
                "external_ref": normalized_external_ref,
            },
        ),
        status=TaskStatus.QUEUED,
        run_id=run_id,
        payload=task_payload,
    )


ACTORS: tuple[ActorLike, ...] = ()

__all__ = [
    "ACTORS",
    "ProviderSweepThreshold",
    "QUEUE_NAME",
    "build_provider_submission_task",
    "get_provider_sweep_threshold",
    "is_terminal_provider_job_status",
    "logger",
]
