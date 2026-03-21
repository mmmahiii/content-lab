"""Outbox event model and publisher protocol for reliable event delivery."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from content_lab_core.models import DomainModel


class DeliveryStatus(str, Enum):
    """Delivery state of an outbox entry."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class OutboxEntry(DomainModel):
    """A single event stored in the transactional outbox before publishing."""

    aggregate_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: int = 0

    def mark_delivered(self) -> None:
        self.status = DeliveryStatus.DELIVERED

    def mark_failed(self) -> None:
        self.status = DeliveryStatus.FAILED
        self.attempts += 1


@runtime_checkable
class OutboxPublisher(Protocol):
    """Interface for draining the outbox and publishing events."""

    def publish(self, entry: OutboxEntry) -> bool: ...
