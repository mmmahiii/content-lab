"""Run trigger/request/response schemas and serialization helpers."""
# mypy: disable-error-code="misc,untyped-decorator"

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from content_lab_api.models.run import Run
from content_lab_api.models.task import Task


def _clean_optional_text(value: str | None, *, field_name: str, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


class WorkflowKey(StrEnum):
    """Named phase-1 flows operators can trigger through the API."""

    DAILY_REEL_FACTORY = "daily_reel_factory"
    PROCESS_REEL = "process_reel"


class FlowTrigger(StrEnum):
    """How a run was initiated."""

    UNKNOWN = "unknown"
    MANUAL = "manual"
    REEL_TRIGGER = "reel_trigger"


class RunCreate(BaseModel):
    """Payload for manually triggering a named workflow."""

    model_config = ConfigDict(extra="forbid")

    workflow_key: WorkflowKey
    input_params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def _normalize_idempotency_key(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, field_name="idempotency_key", max_length=256)


class ReelTriggerCreate(BaseModel):
    """Payload for launching the ``process_reel`` workflow for a reel."""

    model_config = ConfigDict(extra="forbid")

    input_params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def _normalize_idempotency_key(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, field_name="idempotency_key", max_length=256)


class TaskSummaryOut(BaseModel):
    """Operator-facing summary of a task linked to a run."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    task_type: str
    status: str
    idempotency_key: str
    payload: dict[str, Any]
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class RunOut(BaseModel):
    """Serialized run response."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    org_id: uuid.UUID
    workflow_key: str
    flow_trigger: str
    status: str
    idempotency_key: str | None
    external_ref: str | None
    input_params: dict[str, Any]
    output_payload: dict[str, Any] | None
    run_metadata: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RunDetailOut(RunOut):
    """Run detail response enriched with task-level visibility."""

    tasks: list[TaskSummaryOut] = Field(default_factory=list)
    task_status_counts: dict[str, int] = Field(default_factory=dict)


def task_to_summary(task: Task) -> TaskSummaryOut:
    """Build a response payload from the ORM row."""

    return TaskSummaryOut(
        id=task.id,
        task_type=task.task_type,
        status=task.status,
        idempotency_key=task.idempotency_key,
        payload=dict(task.payload or {}),
        result=None if task.result is None else dict(task.result),
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def run_to_out(run: Run) -> RunOut:
    """Build a response payload from the ORM row."""

    return RunOut(
        id=run.id,
        org_id=run.org_id,
        workflow_key=run.workflow_key,
        flow_trigger=run.flow_trigger,
        status=run.status,
        idempotency_key=run.idempotency_key,
        external_ref=run.external_ref,
        input_params=dict(run.input_params or {}),
        output_payload=None if run.output_payload is None else dict(run.output_payload),
        run_metadata=dict(run.run_metadata or {}),
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def run_to_detail(run: Run) -> RunDetailOut:
    """Build a detailed run response including task summaries."""

    tasks = sorted(run.tasks, key=lambda task: (task.created_at, task.id))
    counts = Counter(task.status for task in tasks)
    base = run_to_out(run)
    return RunDetailOut(
        **base.model_dump(),
        tasks=[task_to_summary(task) for task in tasks],
        task_status_counts=dict(sorted(counts.items())),
    )
