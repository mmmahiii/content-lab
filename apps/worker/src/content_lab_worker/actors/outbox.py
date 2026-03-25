"""Outbox worker actor definitions."""

from __future__ import annotations

from typing import Any

from content_lab_worker.actors._shared import ActorLike, build_queue_name, get_actor_logger

logger = get_actor_logger("outbox")
QUEUE_NAME = build_queue_name("outbox")
PROVIDER_JOB_FAILURE_SIGNAL_EVENT = "provider_job.reconciliation_failed"
PROVIDER_JOB_REPAIR_SIGNAL_EVENT = "provider_job.repaired"


def build_provider_job_signal_payload(
    *,
    provider_job_id: str,
    provider: str,
    external_ref: str,
    reconciliation_status: str,
    provider_job_status: str,
    task_status: str | None,
    asset_status: str | None,
    asset_id: str | None = None,
    task_id: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """Build a stable outbox payload for provider-job failure or repair signals."""

    payload: dict[str, Any] = {
        "provider_job_id": provider_job_id,
        "provider": provider,
        "external_ref": external_ref,
        "reconciliation_status": reconciliation_status,
        "provider_job_status": provider_job_status,
        "task_status": task_status,
        "asset_status": asset_status,
    }
    if asset_id is not None:
        payload["asset_id"] = asset_id
    if task_id is not None:
        payload["task_id"] = task_id
    if detail is not None:
        payload["detail"] = detail
    return payload


ACTORS: tuple[ActorLike, ...] = ()

__all__ = [
    "ACTORS",
    "PROVIDER_JOB_FAILURE_SIGNAL_EVENT",
    "PROVIDER_JOB_REPAIR_SIGNAL_EVENT",
    "QUEUE_NAME",
    "build_provider_job_signal_payload",
    "logger",
]
