from __future__ import annotations

from content_lab_outbox.event import DeliveryStatus, OutboxEntry


class TestOutboxEntry:
    def test_defaults(self) -> None:
        entry = OutboxEntry(aggregate_id="run-1", event_type="run.started")
        assert entry.status == DeliveryStatus.PENDING
        assert entry.attempts == 0
        assert entry.payload == {}

    def test_mark_delivered(self) -> None:
        entry = OutboxEntry(aggregate_id="run-1", event_type="run.completed")
        entry.mark_delivered()
        assert entry.status == DeliveryStatus.DELIVERED

    def test_mark_failed_increments(self) -> None:
        entry = OutboxEntry(aggregate_id="run-1", event_type="run.failed")
        entry.mark_failed()
        assert entry.status == DeliveryStatus.FAILED
        assert entry.attempts == 1
        entry.mark_failed()
        assert entry.attempts == 2

    def test_with_payload(self) -> None:
        entry = OutboxEntry(
            aggregate_id="run-2",
            event_type="asset.registered",
            payload={"asset_id": "a-1", "kind": "image"},
        )
        assert entry.payload["asset_id"] == "a-1"
