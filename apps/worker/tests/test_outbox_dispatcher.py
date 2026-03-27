from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from content_lab_outbox import DeliveryStatus, OutboxEntry, SQLOutboxStore, emit_package_ready
from content_lab_outbox.store import OUTBOX_EVENTS
from content_lab_worker.actors.outbox_dispatcher import dispatch_pending_outbox_events


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[str] = []

    def deliver(self, event: OutboxEntry) -> None:
        self.events.append(str(event.id))


class FailingSink:
    def __init__(self, *, message: str = "webhook offline") -> None:
        self.message = message
        self.calls = 0

    def deliver(self, event: OutboxEntry) -> None:
        self.calls += 1
        raise RuntimeError(self.message)


def test_dispatch_pending_outbox_events_marks_sent_with_mocked_sink() -> None:
    session_factory = _session_factory()
    store = SQLOutboxStore(session_factory=session_factory)
    sink = RecordingSink()
    now = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)
    event_id = uuid.uuid4()

    with session_factory.begin() as session:
        emit_package_ready(
            session,
            summary=_package_summary(),
            event_id=event_id,
            created_at=now,
        )

    result = dispatch_pending_outbox_events(
        store=store,
        sink=sink,
        batch_size=10,
        lease_seconds=60,
        now=now,
    )
    stored = store.get_event(event_id=event_id)

    assert result == {"claimed": 1, "sent": 1, "failed": 0}
    assert sink.events == [str(event_id)]
    assert stored.delivery_status == DeliveryStatus.SENT
    assert stored.attempt_count == 1
    assert stored.dispatched_at == now
    assert stored.next_attempt_at is None


def test_dispatch_pending_outbox_events_marks_failure_retryable() -> None:
    session_factory = _session_factory()
    store = SQLOutboxStore(session_factory=session_factory)
    failing_sink = FailingSink()
    retry_sink = RecordingSink()
    now = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)
    event_id = uuid.uuid4()

    with session_factory.begin() as session:
        emit_package_ready(
            session,
            summary=_package_summary(),
            event_id=event_id,
            created_at=now,
        )

    first_result = dispatch_pending_outbox_events(
        store=store,
        sink=failing_sink,
        batch_size=10,
        lease_seconds=60,
        now=now,
    )
    after_failure = store.get_event(event_id=event_id)

    assert first_result == {"claimed": 1, "sent": 0, "failed": 1}
    assert failing_sink.calls == 1
    assert after_failure.delivery_status == DeliveryStatus.FAILED
    assert after_failure.attempt_count == 1
    assert after_failure.next_attempt_at == now + timedelta(seconds=30)

    second_result = dispatch_pending_outbox_events(
        store=store,
        sink=retry_sink,
        batch_size=10,
        lease_seconds=60,
        now=now + timedelta(seconds=30),
    )
    after_retry = store.get_event(event_id=event_id)

    assert second_result == {"claimed": 1, "sent": 1, "failed": 0}
    assert retry_sink.events == [str(event_id)]
    assert after_retry.delivery_status == DeliveryStatus.SENT
    assert after_retry.attempt_count == 2
    assert after_retry.dispatched_at == now + timedelta(seconds=30)
    assert after_retry.next_attempt_at is None


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
