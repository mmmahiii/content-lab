"""Worker actor that drains transactional outbox events."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib import error, request

import dramatiq

from content_lab_outbox import OutboxEntry, SQLOutboxStore
from content_lab_shared.settings import Settings
from content_lab_worker.actors._shared import ActorLike, build_queue_name, get_actor_logger

logger = get_actor_logger("outbox_dispatcher")
QUEUE_NAME = build_queue_name("outbox")
_WEBHOOK_URL_ENV = "CONTENT_LAB_OUTBOX_WEBHOOK_URL"
_WEBHOOK_TIMEOUT_SECONDS = 5.0


class OutboxDispatchStore(Protocol):
    """Persistence operations needed by the dispatcher actor."""

    def claim_events(
        self,
        *,
        limit: int = 50,
        now: datetime | None = None,
        lease_seconds: int = 300,
    ) -> tuple[OutboxEntry, ...]: ...

    def mark_sent(
        self,
        *,
        event: OutboxEntry,
        dispatched_at: datetime | None = None,
    ) -> OutboxEntry: ...

    def mark_failed(
        self,
        *,
        event: OutboxEntry,
        failed_at: datetime | None = None,
    ) -> OutboxEntry: ...


class OutboxSink(Protocol):
    """Delivery sink for dispatched outbox events."""

    def deliver(self, event: OutboxEntry) -> None: ...


class StructuredLoggingSink:
    """Structured log sink used in phase-1 when no webhook is configured."""

    def deliver(self, event: OutboxEntry) -> None:
        logger.info("outbox.dispatch %s", json.dumps(event.as_payload(), sort_keys=True))


class WebhookOutboxSink:
    """Optional webhook delivery sink for operators or local integrations."""

    def __init__(self, *, url: str, timeout_seconds: float = _WEBHOOK_TIMEOUT_SECONDS) -> None:
        self._url = url
        self._timeout_seconds = timeout_seconds

    def deliver(self, event: OutboxEntry) -> None:
        body = json.dumps(event.as_payload(), sort_keys=True).encode("utf-8")
        webhook_request = request.Request(
            self._url,
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(webhook_request, timeout=self._timeout_seconds) as response:
                if response.status >= 400:
                    raise RuntimeError(
                        f"webhook returned HTTP {response.status} for outbox event {event.id}"
                    )
        except error.HTTPError as exc:
            raise RuntimeError(
                f"webhook returned HTTP {exc.code} for outbox event {event.id}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(
                f"webhook delivery failed for outbox event {event.id}: {exc}"
            ) from exc


class CompositeOutboxSink:
    """Fan out to multiple sinks while preserving delivery failures."""

    def __init__(self, *sinks: OutboxSink) -> None:
        self._sinks = sinks

    def deliver(self, event: OutboxEntry) -> None:
        for sink in self._sinks:
            sink.deliver(event)


def build_dispatch_store(*, settings: Settings | None = None) -> SQLOutboxStore:
    """Construct the default SQL-backed outbox store."""

    return SQLOutboxStore(settings=settings or Settings())


def build_dispatch_sink(*, webhook_url: str | None = None) -> OutboxSink:
    """Construct the phase-1 sink: logs always, webhook optionally."""

    sinks: list[OutboxSink] = [StructuredLoggingSink()]
    resolved_webhook_url = webhook_url or _optional_text(os.getenv(_WEBHOOK_URL_ENV))
    if resolved_webhook_url is not None:
        sinks.append(WebhookOutboxSink(url=resolved_webhook_url))
    if len(sinks) == 1:
        return sinks[0]
    return CompositeOutboxSink(*sinks)


def dispatch_pending_outbox_events(
    *,
    store: OutboxDispatchStore | None = None,
    sink: OutboxSink | None = None,
    batch_size: int = 25,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> dict[str, int]:
    """Deliver a batch of claimed outbox events and persist retry metadata."""

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be at least 1")

    current_time = _utcnow(now)
    resolved_store = store or build_dispatch_store()
    resolved_sink = sink or build_dispatch_sink()
    claimed = resolved_store.claim_events(
        limit=batch_size,
        now=current_time,
        lease_seconds=lease_seconds,
    )

    sent_count = 0
    failed_count = 0
    for event in claimed:
        try:
            resolved_sink.deliver(event)
        except Exception as exc:
            failed_event = resolved_store.mark_failed(event=event, failed_at=current_time)
            logger.warning(
                "outbox dispatch failed event_id=%s event_type=%s attempt_count=%s next_attempt_at=%s error=%s",
                event.id,
                event.event_type,
                failed_event.attempt_count,
                None
                if failed_event.next_attempt_at is None
                else failed_event.next_attempt_at.astimezone(UTC).isoformat(),
                exc,
            )
            failed_count += 1
            continue

        sent_event = resolved_store.mark_sent(event=event, dispatched_at=current_time)
        logger.info(
            "outbox dispatch sent event_id=%s event_type=%s attempt_count=%s",
            sent_event.id,
            sent_event.event_type,
            sent_event.attempt_count,
        )
        sent_count += 1

    return {
        "claimed": len(claimed),
        "sent": sent_count,
        "failed": failed_count,
    }


@dramatiq.actor(queue_name=QUEUE_NAME)
def dispatch_outbox(batch_size: int = 25) -> Mapping[str, int]:
    """Drain a batch of pending outbox events."""

    result = dispatch_pending_outbox_events(batch_size=batch_size)
    logger.info("outbox batch complete %s", json.dumps(dict(result), sort_keys=True))
    return result


def _utcnow(value: datetime | None) -> datetime:
    current_time = value or datetime.now(UTC)
    if current_time.tzinfo is None:
        return current_time.replace(tzinfo=UTC)
    return current_time.astimezone(UTC)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


ACTORS: tuple[ActorLike, ...] = (dispatch_outbox,)

__all__ = [
    "ACTORS",
    "CompositeOutboxSink",
    "OutboxDispatchStore",
    "OutboxSink",
    "QUEUE_NAME",
    "StructuredLoggingSink",
    "WebhookOutboxSink",
    "build_dispatch_sink",
    "build_dispatch_store",
    "dispatch_outbox",
    "dispatch_pending_outbox_events",
]
