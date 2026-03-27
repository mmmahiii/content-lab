from __future__ import annotations

from content_lab_outbox.event import DeliveryStatus, OutboxEntry
from content_lab_outbox.process_reel import (
    PROCESS_REEL_FAILURE_EVENT,
    PROCESS_REEL_PACKAGE_READY_EVENT,
    build_process_reel_event_payload,
    process_reel_event_type,
)


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


def test_process_reel_event_helpers_map_ready_and_failure_states() -> None:
    ready_summary = {
        "run_id": "run-1",
        "reel_id": "reel-1",
        "org_id": "org-1",
        "page_id": "page-1",
        "reel_family_id": "family-1",
        "reel_status": "ready",
        "run_status": "succeeded",
        "task_statuses": {"process_reel": "succeeded"},
    }
    failed_summary = {
        **ready_summary,
        "reel_status": "qa_failed",
        "run_status": "failed",
        "error": "qa failed",
    }

    assert process_reel_event_type(ready_summary) == PROCESS_REEL_PACKAGE_READY_EVENT
    assert process_reel_event_type(failed_summary) == PROCESS_REEL_FAILURE_EVENT
    assert build_process_reel_event_payload(failed_summary)["error"] == "qa failed"
