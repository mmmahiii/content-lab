"""Stable terminal event helpers for the phase-1 ``process_reel`` workflow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PROCESS_REEL_FAILURE_EVENT = "process_reel.failed"
PROCESS_REEL_PACKAGE_READY_EVENT = "process_reel.package_ready"


def process_reel_event_type(summary: Mapping[str, Any]) -> str:
    """Map a terminal process-reel summary onto a durable event type."""

    reel_status = str(summary.get("reel_status", "")).strip().lower()
    if reel_status == "ready":
        return PROCESS_REEL_PACKAGE_READY_EVENT
    return PROCESS_REEL_FAILURE_EVENT


def build_process_reel_event_payload(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Build the stable terminal outbox payload for a process-reel run."""

    payload = {
        "run_id": str(summary["run_id"]),
        "reel_id": str(summary["reel_id"]),
        "org_id": str(summary["org_id"]),
        "page_id": str(summary["page_id"]),
        "reel_family_id": str(summary["reel_family_id"]),
        "reel_status": str(summary["reel_status"]),
        "run_status": str(summary["run_status"]),
        "dry_run": bool(summary.get("dry_run", False)),
        "task_statuses": _mapping(summary.get("task_statuses")),
    }
    package_payload = summary.get("package")
    if isinstance(package_payload, Mapping):
        payload["package"] = dict(package_payload)
    error_message = summary.get("error")
    if error_message is not None and str(error_message).strip():
        payload["error"] = str(error_message)
    return payload


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


__all__ = [
    "PROCESS_REEL_FAILURE_EVENT",
    "PROCESS_REEL_PACKAGE_READY_EVENT",
    "build_process_reel_event_payload",
    "process_reel_event_type",
]
