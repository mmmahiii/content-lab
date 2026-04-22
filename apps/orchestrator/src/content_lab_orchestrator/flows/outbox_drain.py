"""Prefect flow to drain the transactional outbox in-process (backup to the worker loop)."""

from __future__ import annotations

import logging
from argparse import Namespace
from typing import Any

from prefect.flows import flow

from content_lab_worker.actors.outbox_dispatcher import dispatch_pending_outbox_events

from .registry import FlowDefinition

logger = logging.getLogger(__name__)


@flow(name="outbox_drain")
def outbox_drain(batch_size: int = 25) -> dict[str, Any]:
    """Deliver pending outbox events using the same logic as the Dramatiq worker actor."""

    result = dispatch_pending_outbox_events(batch_size=batch_size)
    logger.info("outbox_drain finished %s", result)
    return dict(result)


def build_outbox_drain_kwargs(args: Namespace) -> dict[str, object]:
    """Map CLI arguments onto the flow signature."""

    return {"batch_size": args.batch_size}


FLOW_DEFINITION = FlowDefinition(
    name="outbox_drain",
    description="Drain pending transactional outbox events (complements the worker dispatcher loop).",
    entrypoint=outbox_drain,
    build_kwargs=build_outbox_drain_kwargs,
)
