from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from content_lab_outbox import DeliveryStatus
from content_lab_outbox.event import OutboxEntry
from content_lab_worker.actors import outbox_dispatcher as dispatcher_module
from content_lab_worker.actors.outbox_dispatcher import (
    OutboxSink,
    dispatch_pending_outbox_events,
)


class _RecordingStore:
    """In-memory outbox store for dispatcher unit tests."""

    def __init__(self, events: list[OutboxEntry]) -> None:
        self._by_id = {e.id: e for e in events}
        self.mark_sent_ids: list[uuid.UUID] = []
        self.mark_failed_ids: list[uuid.UUID] = []

    def claim_events(
        self,
        *,
        limit: int = 50,
        now: datetime | None = None,
        lease_seconds: int = 300,
    ) -> tuple[OutboxEntry, ...]:
        _ = now, lease_seconds
        pending = [
            e
            for e in self._by_id.values()
            if e.delivery_status == DeliveryStatus.PENDING
        ]
        return tuple(pending[:limit])

    def mark_sent(
        self,
        *,
        event: OutboxEntry,
        dispatched_at: datetime | None = None,
    ) -> OutboxEntry:
        row = self._by_id[event.id]
        row.mark_sent(dispatched_at=dispatched_at)
        self.mark_sent_ids.append(event.id)
        return row

    def mark_failed(
        self,
        *,
        event: OutboxEntry,
        failed_at: datetime | None = None,
    ) -> OutboxEntry:
        _ = failed_at
        row = self._by_id[event.id]
        row.mark_failed(next_attempt_at=None)
        self.mark_failed_ids.append(event.id)
        return row


class _OkSink(OutboxSink):
    def deliver(self, event: OutboxEntry) -> None:
        _ = event


class _FailingSink(OutboxSink):
    def deliver(self, event: OutboxEntry) -> None:
        _ = event
        raise RuntimeError("sink failed")


def _entry(*, event_type: str = "test.event") -> OutboxEntry:
    return OutboxEntry(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        aggregate_type="run",
        aggregate_id=str(uuid.uuid4()),
        event_type=event_type,
        payload={"k": 1},
        created_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC),
    )


def test_dispatch_marks_sent_when_sink_succeeds() -> None:
    event = _entry()
    store = _RecordingStore([event])
    now = datetime(2026, 4, 1, 12, 1, 0, tzinfo=UTC)

    result = dispatch_pending_outbox_events(
        store=store,
        sink=_OkSink(),
        batch_size=10,
        now=now,
    )

    assert result == {"claimed": 1, "sent": 1, "failed": 0}
    assert store.mark_sent_ids == [event.id]
    assert event.delivery_status == DeliveryStatus.SENT
    assert event.dispatched_at is not None


def test_dispatch_marks_failed_when_sink_raises() -> None:
    event = _entry()
    store = _RecordingStore([event])
    now = datetime(2026, 4, 1, 12, 1, 0, tzinfo=UTC)

    result = dispatch_pending_outbox_events(
        store=store,
        sink=_FailingSink(),
        batch_size=10,
        now=now,
    )

    assert result == {"claimed": 1, "sent": 0, "failed": 1}
    assert store.mark_failed_ids == [event.id]
    assert event.delivery_status == DeliveryStatus.FAILED


def test_enqueue_initial_outbox_drain_targets_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: list[object] = []

    def _capture() -> None:
        enqueued.append("sent")

    monkeypatch.setattr(dispatcher_module.dispatch_outbox, "send", _capture)

    dispatcher_module.enqueue_initial_outbox_drain()

    assert enqueued == ["sent"]
