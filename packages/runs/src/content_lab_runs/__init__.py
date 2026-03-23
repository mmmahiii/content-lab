"""Pipeline run lifecycle helpers: correlation context, statuses, idempotency keys."""

from content_lab_runs.context import (
    RunContext,
    correlation_dict,
    current_run_context,
    merge_run_context,
    run_context_scope,
    with_actor,
    with_request_id,
    with_run_id,
    with_task_id,
)
from content_lab_runs.durable import (
    DuplicateIdempotencyKeyError,
    IdempotentResult,
    RunRowSpec,
    TaskRowSpec,
    build_task_idempotency_key,
    task_status_for_run_status,
)
from content_lab_runs.idempotency import (
    JSONValue,
    canonical_json_bytes,
    idempotency_key_from_payload,
)
from content_lab_runs.lifecycle import InvalidTransitionError, RunRecord
from content_lab_runs.status import RunStatus, TaskStatus

__all__ = [
    "DuplicateIdempotencyKeyError",
    "IdempotentResult",
    "InvalidTransitionError",
    "JSONValue",
    "RunContext",
    "RunRecord",
    "RunRowSpec",
    "RunStatus",
    "TaskRowSpec",
    "TaskStatus",
    "build_task_idempotency_key",
    "canonical_json_bytes",
    "correlation_dict",
    "current_run_context",
    "idempotency_key_from_payload",
    "merge_run_context",
    "run_context_scope",
    "task_status_for_run_status",
    "with_actor",
    "with_request_id",
    "with_run_id",
    "with_task_id",
]
