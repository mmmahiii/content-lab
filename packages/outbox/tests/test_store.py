from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from content_lab_outbox import DeliveryStatus
from content_lab_outbox.store import (
    OUTBOX_EVENTS,
    SQLOutboxStore,
    emit_flow_failure,
    emit_package_ready,
)


def test_emit_package_ready_writes_pending_outbox_row() -> None:
    session_factory = _session_factory()
    store = SQLOutboxStore(session_factory=session_factory)
    event_id = uuid.uuid4()
    created_at = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        event = emit_package_ready(
            session,
            summary=_package_summary(),
            event_id=event_id,
            created_at=created_at,
        )

    stored = store.get_event(event_id=event.id)
    assert stored.id == event_id
    assert stored.delivery_status == DeliveryStatus.PENDING
    assert stored.attempt_count == 0
    assert stored.created_at == created_at
    assert stored.payload["package"]["manifest_uri"].endswith("manifest.json")


def test_emit_flow_failure_uses_current_transaction() -> None:
    session_factory = _session_factory()
    store = SQLOutboxStore(session_factory=session_factory)

    with session_factory.begin() as session:
        event = emit_flow_failure(
            session,
            summary=_failure_summary(),
            failed_step="packaging",
            created_at=datetime(2026, 3, 27, 12, 0, tzinfo=UTC),
        )

    stored = store.get_event(event_id=event.id)
    assert stored.event_type == "flow.failed"
    assert stored.payload["failed_step"] == "packaging"
    assert stored.payload["error"] == "manifest write failed"


def test_claim_and_mark_failed_backoff_is_retryable() -> None:
    session_factory = _session_factory()
    store = SQLOutboxStore(session_factory=session_factory)
    event_id = uuid.uuid4()
    created_at = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        emit_package_ready(
            session,
            summary=_package_summary(),
            event_id=event_id,
            created_at=created_at,
        )

    claimed = store.claim_events(now=created_at, limit=1, lease_seconds=120)
    assert [event.id for event in claimed] == [event_id]
    assert claimed[0].next_attempt_at == created_at + timedelta(seconds=120)

    failed = store.mark_failed(event=claimed[0], failed_at=created_at)
    assert failed.delivery_status == DeliveryStatus.FAILED
    assert failed.attempt_count == 1
    assert failed.next_attempt_at == created_at + timedelta(seconds=30)

    assert store.claim_events(now=created_at + timedelta(seconds=29), limit=1) == ()
    retried = store.claim_events(now=created_at + timedelta(seconds=30), limit=1)
    assert [event.id for event in retried] == [event_id]


def test_mark_sent_clears_retry_metadata() -> None:
    session_factory = _session_factory()
    store = SQLOutboxStore(session_factory=session_factory)
    created_at = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        emit_package_ready(
            session,
            summary=_package_summary(),
            event_id=uuid.uuid4(),
            created_at=created_at,
        )

    claimed = store.claim_events(now=created_at, limit=1, lease_seconds=60)
    sent = store.mark_sent(event=claimed[0], dispatched_at=created_at)
    stored = store.get_event(event_id=sent.id)

    assert stored.delivery_status == DeliveryStatus.SENT
    assert stored.attempt_count == 1
    assert stored.dispatched_at == created_at
    assert stored.next_attempt_at is None


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    OUTBOX_EVENTS.create(engine, checkfirst=True)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def _package_summary() -> dict[str, object]:
    org_id = uuid.uuid4()
    return {
        "org_id": str(org_id),
        "run_id": "run-123",
        "reel_id": "reel-123",
        "page_id": "page-123",
        "reel_family_id": "family-123",
        "run_status": "succeeded",
        "reel_status": "ready",
        "package": {
            "manifest_uri": "s3://content-lab/packages/run-123/manifest.json",
            "package_root_uri": "s3://content-lab/packages/run-123",
        },
        "task_statuses": {"packaging": "succeeded"},
    }


def _failure_summary() -> dict[str, object]:
    summary = _package_summary()
    summary["run_status"] = "failed"
    summary["error"] = "manifest write failed"
    summary["task_statuses"] = {"packaging": "failed"}
    summary.pop("package")
    return summary
