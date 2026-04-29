"""Run trigger/request/response schemas and serialization helpers."""
# mypy: disable-error-code="misc,untyped-decorator"

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from content_lab_api.models.run import Run
from content_lab_api.models.task import Task
from content_lab_api.schemas.operator_debug import (
    ProcessReelOperatorDebugOut,
    ProcessReelQASurfaceOut,
    StructuredQAFindingOut,
    build_process_reel_operator_debug,
    resolve_process_reel_qa_surface,
)


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


class OutboxEventItemOut(BaseModel):
    """One transactional outbox row for this run (aggregate id = run)."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    event_type: str
    delivery_status: str
    attempt_count: int
    created_at: datetime
    dispatched_at: datetime | None
    next_attempt_at: datetime | None
    pending_age_seconds: float | None = None


class RunOutboxOut(BaseModel):
    """Outbox delivery visibility for operator-facing run pages."""

    model_config = ConfigDict(extra="forbid")

    events: list[OutboxEventItemOut] = Field(default_factory=list)
    pending_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    has_backlog: bool = False
    summary: str | None = None


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


class RunQaSummaryOut(BaseModel):
    """Compact QA rollup for run detail (structured findings + human-readable failures)."""

    model_config = ConfigDict(extra="forbid")

    passed: bool | None = None
    verdict: str | None = None
    failure_messages: list[str] = Field(default_factory=list)
    structured_findings: list[StructuredQAFindingOut] = Field(default_factory=list)


class RunDetailOut(RunOut):
    """Run detail response enriched with task-level and outbox delivery visibility."""

    tasks: list[TaskSummaryOut] = Field(default_factory=list)
    task_status_counts: dict[str, int] = Field(default_factory=dict)
    outbox: RunOutboxOut = Field(default_factory=RunOutboxOut)
    operator_debug: ProcessReelOperatorDebugOut | None = None
    qa_summary: RunQaSummaryOut | None = None


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


def _run_qa_summary_from_surface(qa: ProcessReelQASurfaceOut | None) -> RunQaSummaryOut | None:
    if qa is None:
        return None
    findings = list(qa.structured_findings)
    messages: list[str] = []
    for row in findings:
        if row.passed:
            continue
        normalized = row.message.strip()
        if not normalized:
            continue
        messages.append(f"[{row.severity}] {row.finding_type}: {normalized}")
    if not messages and qa.passed is False:
        messages.append("QA did not pass; see task results or expand operator debug for gate output.")
    return RunQaSummaryOut(
        passed=qa.passed,
        verdict=qa.verdict,
        failure_messages=messages,
        structured_findings=findings,
    )


def run_to_detail(
    run: Run,
    *,
    outbox: RunOutboxOut | None = None,
    expand_debug: bool = False,
) -> RunDetailOut:
    """Build a detailed run response including task summaries and optional outbox state."""

    tasks = sorted(run.tasks, key=lambda task: (task.created_at, task.id))
    counts = Counter(task.status for task in tasks)
    base = run_to_out(run)
    qa_surface = resolve_process_reel_qa_surface(summary=run.output_payload, tasks=tasks)
    qa_summary = _run_qa_summary_from_surface(qa_surface)
    operator_debug = build_process_reel_operator_debug(
        workflow_key=run.workflow_key,
        summary=run.output_payload,
        tasks=tasks,
        expand_debug=expand_debug,
    )
    return RunDetailOut(
        **base.model_dump(),
        tasks=[task_to_summary(task) for task in tasks],
        task_status_counts=dict(sorted(counts.items())),
        outbox=outbox or RunOutboxOut(),
        operator_debug=operator_debug,
        qa_summary=qa_summary,
    )


def outbox_for_run(
    events: list[Any],  # list[OutboxEvent] to avoid ORM import cycles in typing-only paths
    *,
    now: datetime | None = None,
) -> RunOutboxOut:
    """Turn ORM outbox rows into a compact delivery summary (expects aggregate run scope)."""

    from content_lab_api.models.outbox import OutboxEvent  # local import

    if not events:
        return RunOutboxOut()

    current = now or datetime.now(UTC)
    items: list[OutboxEventItemOut] = []
    pending = sent = failed = 0
    for row in events:
        if not isinstance(row, OutboxEvent):
            continue
        st = (row.delivery_status or "pending").lower()
        if st == "pending":
            pending += 1
        elif st == "sent":
            sent += 1
        else:
            failed += 1
        age: float | None = None
        if st == "pending" and row.created_at is not None:
            created = row.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            age = max(0.0, (current - created.astimezone(UTC)).total_seconds())
        items.append(
            OutboxEventItemOut(
                id=row.id,
                event_type=row.event_type,
                delivery_status=row.delivery_status,
                attempt_count=row.attempt_count,
                created_at=row.created_at,
                dispatched_at=row.dispatched_at,
                next_attempt_at=row.next_attempt_at,
                pending_age_seconds=age,
            )
        )

    has_backlog = pending > 0
    message: str | None = None
    if has_backlog:
        message = (
            f"{pending} notification(s) still pending dispatch; worker outbox drainer is active."
        )
    elif failed > 0 and pending == 0:
        message = f"{failed} outbox event(s) failed delivery; see attempt_count and next_attempt_at for retries."
    elif sent > 0 and not has_backlog:
        message = "All recorded outbox events for this run have been dispatched."

    return RunOutboxOut(
        events=items,
        pending_count=pending,
        sent_count=sent,
        failed_count=failed,
        has_backlog=has_backlog,
        summary=message,
    )
