from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from content_lab_outbox.event import (
    FLOW_FAILURE_EVENT,
    PACKAGE_READY_EVENT,
    DeliveryStatus,
    OutboxEntry,
    build_flow_failure_event,
    build_package_ready_event,
)
from content_lab_outbox.process_reel import (
    PROCESS_REEL_FAILURE_EVENT,
    PROCESS_REEL_PACKAGE_READY_EVENT,
    build_process_reel_event_payload,
    process_reel_event_type,
)


class TestOutboxEntry:
    def test_defaults(self) -> None:
        entry = OutboxEntry(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            aggregate_type="run",
            aggregate_id="run-1",
            event_type="run.started",
        )
        assert entry.delivery_status == DeliveryStatus.PENDING
        assert entry.attempt_count == 0
        assert entry.payload == {}

    def test_mark_sent(self) -> None:
        entry = OutboxEntry(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            aggregate_type="run",
            aggregate_id="run-1",
            event_type="run.completed",
        )
        sent_at = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)
        entry.mark_sent(dispatched_at=sent_at)
        assert entry.delivery_status == DeliveryStatus.SENT
        assert entry.attempt_count == 1
        assert entry.dispatched_at == sent_at

    def test_mark_failed_increments(self) -> None:
        entry = OutboxEntry(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            aggregate_type="run",
            aggregate_id="run-1",
            event_type="run.failed",
        )
        retry_at = datetime(2026, 3, 27, 12, 0, tzinfo=UTC) + timedelta(seconds=30)
        entry.mark_failed(next_attempt_at=retry_at)
        assert entry.delivery_status == DeliveryStatus.FAILED
        assert entry.attempt_count == 1
        assert entry.next_attempt_at == retry_at
        entry.mark_failed(next_attempt_at=retry_at + timedelta(seconds=30))
        assert entry.attempt_count == 2

    def test_with_payload(self) -> None:
        entry = OutboxEntry(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            aggregate_type="asset",
            aggregate_id="run-2",
            event_type="asset.registered",
            payload={"asset_id": "a-1", "kind": "image"},
        )
        assert entry.payload["asset_id"] == "a-1"


def test_build_package_ready_event_uses_summary_payload() -> None:
    org_id = uuid.uuid4()
    spec = build_package_ready_event(
        summary={
            "org_id": str(org_id),
            "run_id": "run-123",
            "reel_id": "reel-123",
            "run_status": "succeeded",
            "reel_status": "ready",
            "package": {"manifest_uri": "s3://content-lab/packages/run-123/manifest.json"},
            "task_statuses": {"packaging": "succeeded"},
        }
    )

    assert spec.org_id == org_id
    assert spec.aggregate_type == "run"
    assert spec.aggregate_id == "run-123"
    assert spec.event_type == PACKAGE_READY_EVENT
    assert spec.payload["package"]["manifest_uri"].endswith("manifest.json")


def test_build_flow_failure_event_requires_error_context() -> None:
    org_id = uuid.uuid4()
    spec = build_flow_failure_event(
        summary={
            "org_id": str(org_id),
            "run_id": "run-123",
            "reel_id": "reel-123",
            "run_status": "failed",
            "error": "packaging checksum mismatch",
            "task_statuses": {"packaging": "failed"},
        },
        failed_step="packaging",
    )

    assert spec.org_id == org_id
    assert spec.aggregate_id == "run-123"
    assert spec.event_type == FLOW_FAILURE_EVENT
    assert spec.payload["failed_step"] == "packaging"
    assert spec.payload["error"] == "packaging checksum mismatch"


def test_build_flow_failure_event_rejects_missing_error() -> None:
    with pytest.raises(ValueError, match="failure summaries must include an error"):
        build_flow_failure_event(
            summary={
                "org_id": str(uuid.uuid4()),
                "run_id": "run-123",
            }
        )


def test_process_reel_event_helpers_map_ready_and_failure_states() -> None:
    ready_summary = {
        "run_id": "run-1",
        "reel_id": "reel-1",
        "org_id": str(uuid.uuid4()),
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
