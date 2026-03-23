"""Durable run/task persistence helpers backed by the phase-1 schema."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from content_lab_api.models.run import Run
from content_lab_api.models.task import Task
from content_lab_runs import (
    DuplicateIdempotencyKeyError,
    IdempotentResult,
    RunRowSpec,
    TaskRowSpec,
)

_RUN_IDEMPOTENCY_CONSTRAINT = "uq_runs_org_idempotency_key"
_TASK_IDEMPOTENCY_CONSTRAINT = "uq_tasks_org_idempotency_key"


def _error_message(exc: IntegrityError) -> str:
    return str(exc.orig if exc.orig is not None else exc)


def _has_constraint(exc: IntegrityError, *, name: str) -> bool:
    return name in _error_message(exc)


def _as_uuid(value: str | uuid.UUID, *, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return uuid.UUID(normalized)


def _as_optional_uuid(
    value: str | uuid.UUID | None,
    *,
    field_name: str,
) -> uuid.UUID | None:
    if value is None:
        return None
    return _as_uuid(value, field_name=field_name)


def get_run_by_idempotency_key(
    db: Session,
    *,
    org_id: uuid.UUID,
    idempotency_key: str,
) -> Run | None:
    return (
        db.query(Run)
        .filter(Run.org_id == org_id, Run.idempotency_key == idempotency_key)
        .one_or_none()
    )


def get_task_by_idempotency_key(
    db: Session,
    *,
    org_id: uuid.UUID,
    idempotency_key: str,
) -> Task | None:
    return (
        db.query(Task)
        .filter(Task.org_id == org_id, Task.idempotency_key == idempotency_key)
        .one_or_none()
    )


def create_run_row(db: Session, *, spec: RunRowSpec) -> Run:
    run = Run(
        org_id=_as_uuid(spec.org_id, field_name="org_id"),
        workflow_key=spec.workflow_key,
        flow_trigger=spec.flow_trigger,
        idempotency_key=spec.idempotency_key,
        status=spec.status.value,
        input_params=dict(spec.input_params),
        external_ref=spec.external_ref,
        output_payload=None if spec.output_payload is None else dict(spec.output_payload),
        run_metadata=dict(spec.run_metadata),
    )

    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError as exc:
        if spec.idempotency_key is not None and _has_constraint(
            exc, name=_RUN_IDEMPOTENCY_CONSTRAINT
        ):
            raise DuplicateIdempotencyKeyError(
                record_type="run",
                idempotency_key=spec.idempotency_key,
            ) from exc
        raise

    return run


def create_task_row(db: Session, *, spec: TaskRowSpec) -> Task:
    task = Task(
        org_id=_as_uuid(spec.org_id, field_name="org_id"),
        task_type=spec.task_type,
        idempotency_key=spec.idempotency_key,
        status=spec.status.value,
        run_id=_as_optional_uuid(spec.run_id, field_name="run_id"),
        payload=dict(spec.payload),
        result=None if spec.result is None else dict(spec.result),
    )

    try:
        with db.begin_nested():
            db.add(task)
            db.flush()
    except IntegrityError as exc:
        if _has_constraint(exc, name=_TASK_IDEMPOTENCY_CONSTRAINT):
            raise DuplicateIdempotencyKeyError(
                record_type="task",
                idempotency_key=spec.idempotency_key,
            ) from exc
        raise

    return task


def ensure_task_row(db: Session, *, spec: TaskRowSpec) -> IdempotentResult[Task]:
    org_id = _as_uuid(spec.org_id, field_name="org_id")
    existing = get_task_by_idempotency_key(db, org_id=org_id, idempotency_key=spec.idempotency_key)
    if existing is not None:
        return IdempotentResult(record=existing, created=False)

    try:
        task = create_task_row(db, spec=spec)
    except DuplicateIdempotencyKeyError:
        existing = get_task_by_idempotency_key(
            db,
            org_id=org_id,
            idempotency_key=spec.idempotency_key,
        )
        if existing is None:
            raise
        return IdempotentResult(record=existing, created=False)

    return IdempotentResult(record=task, created=True)


def apply_task_row_spec(task: Task, *, spec: TaskRowSpec) -> Task:
    task.status = spec.status.value
    task.payload = dict(spec.payload)
    task.result = None if spec.result is None else dict(spec.result)
    task.run_id = _as_optional_uuid(spec.run_id, field_name="run_id")
    return task
