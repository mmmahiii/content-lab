"""SQL-backed helpers for writing and dispatching transactional outbox events."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.orm import Session, sessionmaker

from content_lab_outbox.event import (
    DeliveryStatus,
    OutboxEntry,
    OutboxEventSpec,
    build_flow_failure_event,
    build_package_ready_event,
)
from content_lab_shared.settings import Settings

_METADATA = sa.MetaData()
OUTBOX_EVENTS = sa.Table(
    "outbox_events",
    _METADATA,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("aggregate_type", sa.String(length=128), nullable=False),
    sa.Column("aggregate_id", sa.String(length=256), nullable=False),
    sa.Column("event_type", sa.String(length=128), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("delivery_status", sa.String(length=32), nullable=False),
    sa.Column("attempt_count", sa.Integer(), nullable=False),
    sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

_RETRYABLE_STATUSES = (DeliveryStatus.PENDING.value, DeliveryStatus.FAILED.value)
_MISSING = object()


def emit_outbox_event(
    session: Session,
    *,
    spec: OutboxEventSpec,
    event_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> OutboxEntry:
    """Insert an outbox row using the caller's active transaction."""

    current_time = _utcnow(created_at)
    row_id = event_id or uuid.uuid4()
    session.execute(
        OUTBOX_EVENTS.insert().values(
            id=row_id,
            org_id=spec.org_id,
            aggregate_type=spec.aggregate_type,
            aggregate_id=spec.aggregate_id,
            event_type=spec.event_type,
            payload=dict(spec.payload),
            delivery_status=DeliveryStatus.PENDING.value,
            attempt_count=0,
            next_attempt_at=None,
            dispatched_at=None,
            created_at=current_time,
        )
    )
    session.flush()
    return OutboxEntry(
        id=row_id,
        org_id=spec.org_id,
        aggregate_type=spec.aggregate_type,
        aggregate_id=spec.aggregate_id,
        event_type=spec.event_type,
        payload=dict(spec.payload),
        delivery_status=DeliveryStatus.PENDING,
        attempt_count=0,
        next_attempt_at=None,
        dispatched_at=None,
        created_at=current_time,
    )


def emit_package_ready(
    session: Session,
    *,
    summary: Mapping[str, Any],
    event_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> OutboxEntry:
    """Emit a package-ready notification inside the current transaction."""

    return emit_outbox_event(
        session,
        spec=build_package_ready_event(summary=summary),
        event_id=event_id,
        created_at=created_at,
    )


def emit_flow_failure(
    session: Session,
    *,
    summary: Mapping[str, Any],
    failed_step: str | None = None,
    detail: str | None = None,
    event_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> OutboxEntry:
    """Emit a flow-failure notification inside the current transaction."""

    return emit_outbox_event(
        session,
        spec=build_flow_failure_event(summary=summary, failed_step=failed_step, detail=detail),
        event_id=event_id,
        created_at=created_at,
    )


def compute_next_attempt_at(
    *,
    attempt_count: int,
    now: datetime | None = None,
    base_delay_seconds: int = 30,
    max_delay_seconds: int = 3600,
) -> datetime:
    """Compute exponential backoff for the next delivery attempt."""

    if attempt_count < 1:
        raise ValueError("attempt_count must be at least 1")
    if base_delay_seconds < 1:
        raise ValueError("base_delay_seconds must be at least 1")
    if max_delay_seconds < base_delay_seconds:
        raise ValueError("max_delay_seconds must be >= base_delay_seconds")

    exponent = attempt_count - 1
    delay_seconds = min(base_delay_seconds * (2**exponent), max_delay_seconds)
    return _utcnow(now) + timedelta(seconds=delay_seconds)


class SQLOutboxStore:
    """SQL-backed store used by the worker dispatcher actor."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        if session_factory is None:
            resolved_settings = settings or Settings()
            resolved_engine = engine or create_engine(
                resolved_settings.database_url,
                pool_pre_ping=True,
            )
            session_factory = sessionmaker(
                bind=resolved_engine,
                class_=Session,
                expire_on_commit=False,
            )
        self._session_factory = session_factory

    def claim_events(
        self,
        *,
        limit: int = 50,
        now: datetime | None = None,
        lease_seconds: int = 300,
    ) -> tuple[OutboxEntry, ...]:
        """Lease pending or previously failed events so a dispatcher can deliver them."""

        if limit < 1:
            raise ValueError("limit must be at least 1")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be at least 1")

        current_time = _utcnow(now)
        lease_until = current_time + timedelta(seconds=lease_seconds)
        with self._session_factory.begin() as session:
            statement = (
                sa.select(OUTBOX_EVENTS)
                .where(
                    OUTBOX_EVENTS.c.delivery_status.in_(_RETRYABLE_STATUSES),
                    sa.or_(
                        OUTBOX_EVENTS.c.next_attempt_at.is_(None),
                        OUTBOX_EVENTS.c.next_attempt_at <= current_time,
                    ),
                )
                .order_by(
                    sa.func.coalesce(OUTBOX_EVENTS.c.next_attempt_at, OUTBOX_EVENTS.c.created_at),
                    OUTBOX_EVENTS.c.created_at,
                )
                .limit(limit)
            )
            if _supports_skip_locked(session):
                statement = statement.with_for_update(skip_locked=True)

            rows = session.execute(statement).mappings().all()
            if not rows:
                return ()

            row_ids = [_row_uuid(row["id"], field_name="id") for row in rows]
            session.execute(
                sa.update(OUTBOX_EVENTS)
                .where(OUTBOX_EVENTS.c.id.in_(row_ids))
                .values(next_attempt_at=lease_until)
            )
            return tuple(_entry_from_row(row, next_attempt_at=lease_until) for row in rows)

    def mark_sent(
        self,
        *,
        event: OutboxEntry,
        dispatched_at: datetime | None = None,
    ) -> OutboxEntry:
        """Mark an event as sent after a successful delivery."""

        current_time = _utcnow(dispatched_at)
        updated_attempt_count = event.attempt_count + 1
        with self._session_factory.begin() as session:
            session.execute(
                sa.update(OUTBOX_EVENTS)
                .where(OUTBOX_EVENTS.c.id == event.id)
                .values(
                    delivery_status=DeliveryStatus.SENT.value,
                    attempt_count=updated_attempt_count,
                    next_attempt_at=None,
                    dispatched_at=current_time,
                )
            )
        return OutboxEntry(
            id=event.id,
            org_id=event.org_id,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
            payload=dict(event.payload),
            delivery_status=DeliveryStatus.SENT,
            attempt_count=updated_attempt_count,
            next_attempt_at=None,
            dispatched_at=current_time,
            created_at=event.created_at,
        )

    def mark_failed(
        self,
        *,
        event: OutboxEntry,
        failed_at: datetime | None = None,
    ) -> OutboxEntry:
        """Mark an event as failed and schedule it for another attempt."""

        current_time = _utcnow(failed_at)
        updated_attempt_count = event.attempt_count + 1
        next_attempt_at = compute_next_attempt_at(
            attempt_count=updated_attempt_count,
            now=current_time,
        )
        with self._session_factory.begin() as session:
            session.execute(
                sa.update(OUTBOX_EVENTS)
                .where(OUTBOX_EVENTS.c.id == event.id)
                .values(
                    delivery_status=DeliveryStatus.FAILED.value,
                    attempt_count=updated_attempt_count,
                    next_attempt_at=next_attempt_at,
                )
            )
        return OutboxEntry(
            id=event.id,
            org_id=event.org_id,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
            payload=dict(event.payload),
            delivery_status=DeliveryStatus.FAILED,
            attempt_count=updated_attempt_count,
            next_attempt_at=next_attempt_at,
            dispatched_at=event.dispatched_at,
            created_at=event.created_at,
        )

    def get_event(self, *, event_id: uuid.UUID | str) -> OutboxEntry:
        """Load a single outbox event for assertions and inspection."""

        row_id = _row_uuid(event_id, field_name="event_id")
        with self._session_factory() as session:
            row = (
                session.execute(sa.select(OUTBOX_EVENTS).where(OUTBOX_EVENTS.c.id == row_id))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise LookupError(f"Outbox event {row_id} was not found")
            return _entry_from_row(row)


def _entry_from_row(
    row: RowMapping,
    *,
    next_attempt_at: datetime | None | object = _MISSING,
) -> OutboxEntry:
    resolved_next_attempt_at = (
        _row_datetime(row["next_attempt_at"], field_name="next_attempt_at")
        if next_attempt_at is _MISSING
        else _optional_datetime(next_attempt_at, field_name="next_attempt_at")
    )
    return OutboxEntry(
        id=_row_uuid(row["id"], field_name="id"),
        org_id=_row_uuid(row["org_id"], field_name="org_id"),
        aggregate_type=str(row["aggregate_type"]),
        aggregate_id=str(row["aggregate_id"]),
        event_type=str(row["event_type"]),
        payload=_mapping(row["payload"]),
        delivery_status=DeliveryStatus(str(row["delivery_status"])),
        attempt_count=int(row["attempt_count"]),
        next_attempt_at=resolved_next_attempt_at,
        dispatched_at=_row_datetime(row["dispatched_at"], field_name="dispatched_at"),
        created_at=_required_datetime(row["created_at"], field_name="created_at"),
    )


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _utcnow(value: datetime | None) -> datetime:
    current_time = value or datetime.now(UTC)
    if current_time.tzinfo is None:
        return current_time.replace(tzinfo=UTC)
    return current_time.astimezone(UTC)


def _row_uuid(value: Any, *, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if value is None:
        raise ValueError(f"{field_name} must not be null")
    return uuid.UUID(str(value))


def _required_datetime(value: Any, *, field_name: str) -> datetime:
    resolved = _optional_datetime(value, field_name=field_name)
    if resolved is None:
        raise ValueError(f"{field_name} must not be null")
    return resolved


def _row_datetime(value: Any, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _required_datetime(value, field_name=field_name)


def _optional_datetime(value: Any, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _utcnow(value)
    raise ValueError(f"{field_name} must be a datetime or null")


def _supports_skip_locked(session: Session) -> bool:
    bind = session.get_bind()
    return bind is not None and bind.dialect.name != "sqlite"


__all__ = [
    "OUTBOX_EVENTS",
    "SQLOutboxStore",
    "compute_next_attempt_at",
    "emit_flow_failure",
    "emit_outbox_event",
    "emit_package_ready",
]
