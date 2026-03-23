"""Reusable durable run/task row specs and idempotency helpers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Generic, TypeVar
from uuid import UUID

from content_lab_runs.idempotency import JSONValue, idempotency_key_from_payload
from content_lab_runs.status import RunStatus, TaskStatus

RecordId = str | UUID
_T = TypeVar("_T")


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_required_text(value, field_name=field_name)


def _normalize_record_id(value: RecordId, *, field_name: str) -> RecordId:
    if isinstance(value, str):
        return _normalize_required_text(value, field_name=field_name)
    return value


def _normalize_optional_record_id(
    value: RecordId | None,
    *,
    field_name: str,
) -> RecordId | None:
    if value is None:
        return None
    return _normalize_record_id(value, field_name=field_name)


def _copy_mapping(value: dict[str, Any] | None) -> dict[str, Any]:
    return {} if value is None else dict(value)


def _copy_optional_mapping(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if value is None else dict(value)


def build_task_idempotency_key(
    task_type: str,
    *,
    payload: dict[str, JSONValue] | None = None,
    token: str | None = None,
) -> str:
    """Build a deterministic task idempotency key.

    ``payload`` produces a stable hashed key, while ``token`` preserves a readable
    ``task_type:token`` shape for pre-hashed identifiers such as asset keys.
    """

    normalized_task_type = _normalize_required_text(task_type, field_name="task_type")
    if (payload is None) == (token is None):
        raise ValueError("provide exactly one of payload or token")

    if token is not None:
        normalized_token = _normalize_required_text(token, field_name="token")
        key = f"{normalized_task_type}:{normalized_token}"
        if len(key) > 256:
            raise ValueError("task idempotency key must be at most 256 characters")
        return key

    return idempotency_key_from_payload(normalized_task_type, payload or {})


def task_status_for_run_status(run_status: str | RunStatus) -> TaskStatus:
    """Translate a run-level status into the closest task-level state."""

    normalized = RunStatus(run_status)
    mapping = {
        RunStatus.PENDING: TaskStatus.PENDING,
        RunStatus.QUEUED: TaskStatus.QUEUED,
        RunStatus.RUNNING: TaskStatus.RUNNING,
        RunStatus.SUCCEEDED: TaskStatus.SUCCEEDED,
        RunStatus.FAILED: TaskStatus.FAILED,
        RunStatus.CANCELLED: TaskStatus.SKIPPED,
    }
    return mapping.get(normalized, TaskStatus.PENDING)


@dataclass(frozen=True, slots=True)
class DuplicateIdempotencyKeyError(RuntimeError):
    """Raised when a durable run/task insert hits an idempotency collision."""

    record_type: str
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_type",
            _normalize_required_text(self.record_type, field_name="record_type"),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _normalize_required_text(self.idempotency_key, field_name="idempotency_key"),
        )

    def __str__(self) -> str:
        return f"duplicate {self.record_type} idempotency key: {self.idempotency_key}"


@dataclass(frozen=True, slots=True)
class IdempotentResult(Generic[_T]):
    """Result of an idempotent create-or-fetch operation."""

    record: _T
    created: bool

    @property
    def duplicate(self) -> bool:
        return not self.created


@dataclass(frozen=True, slots=True)
class RunRowSpec:
    """Portable run-row values shared across API, worker, and orchestrator."""

    org_id: RecordId
    workflow_key: str
    flow_trigger: str = "unknown"
    idempotency_key: str | None = None
    status: RunStatus = RunStatus.PENDING
    input_params: dict[str, Any] = field(default_factory=dict)
    external_ref: str | None = None
    output_payload: dict[str, Any] | None = None
    run_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "org_id", _normalize_record_id(self.org_id, field_name="org_id"))
        object.__setattr__(
            self,
            "workflow_key",
            _normalize_required_text(self.workflow_key, field_name="workflow_key"),
        )
        object.__setattr__(
            self,
            "flow_trigger",
            _normalize_required_text(self.flow_trigger, field_name="flow_trigger"),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _normalize_optional_text(self.idempotency_key, field_name="idempotency_key"),
        )
        object.__setattr__(
            self,
            "external_ref",
            _normalize_optional_text(self.external_ref, field_name="external_ref"),
        )
        object.__setattr__(self, "input_params", _copy_mapping(self.input_params))
        object.__setattr__(self, "output_payload", _copy_optional_mapping(self.output_payload))
        object.__setattr__(self, "run_metadata", _copy_mapping(self.run_metadata))

    def as_row(self) -> dict[str, object]:
        return {
            "org_id": self.org_id,
            "workflow_key": self.workflow_key,
            "flow_trigger": self.flow_trigger,
            "idempotency_key": self.idempotency_key,
            "status": self.status.value,
            "input_params": dict(self.input_params),
            "external_ref": self.external_ref,
            "output_payload": None if self.output_payload is None else dict(self.output_payload),
            "run_metadata": dict(self.run_metadata),
        }


@dataclass(frozen=True, slots=True)
class TaskRowSpec:
    """Portable task-row values plus canonical task-state transitions."""

    org_id: RecordId
    task_type: str
    idempotency_key: str
    status: TaskStatus = TaskStatus.PENDING
    run_id: RecordId | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "org_id", _normalize_record_id(self.org_id, field_name="org_id"))
        object.__setattr__(
            self,
            "task_type",
            _normalize_required_text(self.task_type, field_name="task_type"),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _normalize_required_text(self.idempotency_key, field_name="idempotency_key"),
        )
        object.__setattr__(
            self,
            "run_id",
            _normalize_optional_record_id(self.run_id, field_name="run_id"),
        )
        object.__setattr__(self, "payload", _copy_mapping(self.payload))
        object.__setattr__(self, "result", _copy_optional_mapping(self.result))

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.SKIPPED,
            TaskStatus.CANCELLED,
        }

    def as_row(self) -> dict[str, object]:
        return {
            "org_id": self.org_id,
            "task_type": self.task_type,
            "idempotency_key": self.idempotency_key,
            "status": self.status.value,
            "run_id": self.run_id,
            "payload": dict(self.payload),
            "result": None if self.result is None else dict(self.result),
        }

    def queued(self, *, payload: dict[str, Any] | None = None) -> TaskRowSpec:
        return self._with_status(TaskStatus.QUEUED, payload=payload)

    def running(self, *, payload: dict[str, Any] | None = None) -> TaskRowSpec:
        return self._with_status(TaskStatus.RUNNING, payload=payload)

    def retrying(
        self,
        *,
        payload: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> TaskRowSpec:
        return self._with_status(TaskStatus.RETRYING, payload=payload, result=result)

    def succeeded(
        self,
        *,
        payload: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> TaskRowSpec:
        return self._with_status(TaskStatus.SUCCEEDED, payload=payload, result=result)

    def failed(
        self,
        *,
        payload: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> TaskRowSpec:
        return self._with_status(TaskStatus.FAILED, payload=payload, result=result)

    def skipped(
        self,
        *,
        payload: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> TaskRowSpec:
        return self._with_status(TaskStatus.SKIPPED, payload=payload, result=result)

    def _with_status(
        self,
        status: TaskStatus,
        *,
        payload: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> TaskRowSpec:
        next_payload = self.payload if payload is None else dict(payload)
        next_result = self.result if result is None else dict(result)
        return replace(self, status=status, payload=next_payload, result=next_result)
