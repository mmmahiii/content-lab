"""Provider-facing worker actor definitions."""

from __future__ import annotations

from typing import Any

from content_lab_runs import TaskRowSpec, TaskStatus, build_task_idempotency_key
from content_lab_worker.actors._shared import ActorLike, build_queue_name, get_actor_logger

logger = get_actor_logger("provider")
QUEUE_NAME = build_queue_name("provider")
_PROVIDER_SUBMISSION_TASK_TYPE = "provider.submit"


def build_provider_submission_task(
    *,
    org_id: str,
    provider: str,
    external_ref: str,
    run_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> TaskRowSpec:
    """Build a durable task envelope for a provider submission/polling cycle."""

    normalized_provider = provider.strip().lower()
    normalized_external_ref = external_ref.strip()
    if not normalized_provider:
        raise ValueError("provider must not be blank")
    if not normalized_external_ref:
        raise ValueError("external_ref must not be blank")
    task_payload = {
        "provider": normalized_provider,
        "external_ref": normalized_external_ref,
        **({} if payload is None else dict(payload)),
    }
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

__all__ = ["ACTORS", "QUEUE_NAME", "build_provider_submission_task", "logger"]
