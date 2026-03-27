"""Outbox event models and flow-friendly notification builders."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

PACKAGE_READY_EVENT = "package.ready"
FLOW_FAILURE_EVENT = "flow.failed"


class DeliveryStatus(str, Enum):
    """Delivery state of an outbox entry."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OutboxEventSpec:
    """A transactional outbox event ready to be written inside a DB transaction."""

    org_id: uuid.UUID
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OutboxEntry:
    """A materialized outbox row used by emitters and the dispatcher actor."""

    id: uuid.UUID
    org_id: uuid.UUID
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING
    attempt_count: int = 0
    next_attempt_at: datetime | None = None
    dispatched_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def mark_sent(self, *, dispatched_at: datetime | None = None) -> None:
        self.delivery_status = DeliveryStatus.SENT
        self.attempt_count += 1
        self.dispatched_at = dispatched_at or datetime.now(UTC)
        self.next_attempt_at = None

    def mark_failed(self, *, next_attempt_at: datetime | None = None) -> None:
        self.delivery_status = DeliveryStatus.FAILED
        self.attempt_count += 1
        self.next_attempt_at = next_attempt_at

    def as_payload(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "org_id": str(self.org_id),
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "delivery_status": self.delivery_status.value,
            "attempt_count": self.attempt_count,
            "next_attempt_at": None
            if self.next_attempt_at is None
            else self.next_attempt_at.astimezone(UTC).isoformat(),
            "dispatched_at": None
            if self.dispatched_at is None
            else self.dispatched_at.astimezone(UTC).isoformat(),
            "created_at": self.created_at.astimezone(UTC).isoformat(),
        }


def build_package_ready_event(
    *,
    summary: Mapping[str, Any],
    aggregate_type: str = "run",
) -> OutboxEventSpec:
    """Build a package-ready notification payload directly from a flow summary."""

    package = _mapping(summary.get("package"))
    if not package:
        raise ValueError("package-ready summaries must include a non-empty package payload")

    run_id = _required_text(summary, "run_id")
    org_id = _required_uuid(summary, "org_id")
    payload = _compact_payload(
        {
            "org_id": str(org_id),
            "run_id": run_id,
            "reel_id": _optional_text(summary.get("reel_id")),
            "page_id": _optional_text(summary.get("page_id")),
            "reel_family_id": _optional_text(summary.get("reel_family_id")),
            "run_status": _optional_text(summary.get("run_status")),
            "reel_status": _optional_text(summary.get("reel_status")),
            "dry_run": bool(summary.get("dry_run", False)),
            "package": package,
            "task_statuses": _mapping(summary.get("task_statuses")),
        }
    )
    return OutboxEventSpec(
        org_id=org_id,
        aggregate_type=aggregate_type,
        aggregate_id=run_id,
        event_type=PACKAGE_READY_EVENT,
        payload=payload,
    )


def build_flow_failure_event(
    *,
    summary: Mapping[str, Any],
    failed_step: str | None = None,
    detail: str | None = None,
    aggregate_type: str = "run",
    event_type: str = FLOW_FAILURE_EVENT,
) -> OutboxEventSpec:
    """Build a stable failure-notification payload from a flow summary."""

    run_id = _required_text(summary, "run_id")
    org_id = _required_uuid(summary, "org_id")
    error_message = detail or _optional_text(summary.get("error"))
    if error_message is None:
        raise ValueError("failure summaries must include an error or explicit detail")

    payload = _compact_payload(
        {
            "org_id": str(org_id),
            "run_id": run_id,
            "reel_id": _optional_text(summary.get("reel_id")),
            "page_id": _optional_text(summary.get("page_id")),
            "reel_family_id": _optional_text(summary.get("reel_family_id")),
            "run_status": _optional_text(summary.get("run_status")),
            "reel_status": _optional_text(summary.get("reel_status")),
            "failed_step": failed_step,
            "error": error_message,
            "task_statuses": _mapping(summary.get("task_statuses")),
            "step_outputs": _mapping(summary.get("step_outputs")),
        }
    )
    return OutboxEventSpec(
        org_id=org_id,
        aggregate_type=aggregate_type,
        aggregate_id=run_id,
        event_type=event_type,
        payload=payload,
    )


@runtime_checkable
class OutboxPublisher(Protocol):
    """Interface for draining the outbox and publishing events."""

    def publish(self, entry: OutboxEntry) -> bool: ...


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = _optional_text(payload.get(key))
    if value is None:
        raise ValueError(f"{key} must be present and non-empty")
    return value


def _required_uuid(payload: Mapping[str, Any], key: str) -> uuid.UUID:
    return uuid.UUID(_required_text(payload, key))


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _compact_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            continue
        compact[key] = value
    return compact
