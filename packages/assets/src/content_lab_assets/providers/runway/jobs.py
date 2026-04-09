"""Shared Runway provider-job helpers for submission, polling, and final results."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from content_lab_assets.canonicalise import normalize_identifier
from content_lab_shared.logging import redact_sensitive_string

RUNWAY_PROVIDER = "runway"
_RUNWAY_EXTERNAL_REF_PREFIX = "runway-gen45"
_REDACTED = "***REDACTED***"
_SENSITIVE_KEY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(api[_-]?key|authorization|cookie|credential|key|password|secret|token)", re.I),
)


class RunwayJobStatus(StrEnum):
    """Durable provider-job states mirrored from the external Runway lifecycle."""

    SUBMITTED = "submitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


def normalize_runway_job_status(status: str | RunwayJobStatus) -> RunwayJobStatus:
    """Return a canonical Runway provider-job status."""

    return RunwayJobStatus(str(status).strip().lower())


def build_runway_job_external_ref(*, asset_key_hash: str) -> str:
    """Build the deterministic registry key for provider_jobs (not Runway's /v1/tasks/{uuid} id)."""

    normalized_hash = normalize_identifier(asset_key_hash, field_name="asset_key_hash")
    return f"{_RUNWAY_EXTERNAL_REF_PREFIX}:{normalized_hash}"


def is_runway_registry_external_ref(external_ref: str) -> bool:
    """True when ``external_ref`` is our stable registry key (``runway-gen45:…``), not a Runway task UUID."""

    normalized = str(external_ref).strip()
    return normalized.startswith(f"{_RUNWAY_EXTERNAL_REF_PREFIX}:")


def runway_provider_api_task_id_from_metadata(metadata: Mapping[str, Any]) -> str | None:
    """Return the Runway task UUID from merged provider_job metadata, if present."""

    submission = metadata.get("submission")
    if isinstance(submission, Mapping):
        parsed = _optional_uuid_string(submission.get("task_id"))
        if parsed is not None:
            return parsed
    snapshots = metadata.get("snapshots")
    if isinstance(snapshots, Mapping):
        snap = snapshots.get("submission")
        if isinstance(snap, Mapping):
            for key in ("response", "provider_payload"):
                block = snap.get(key)
                if isinstance(block, Mapping):
                    parsed = _optional_uuid_string(block.get("id"))
                    if parsed is not None:
                        return parsed
    return None


def _optional_uuid_string(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    try:
        uuid.UUID(candidate)
    except ValueError:
        return None
    return candidate


def sanitize_provider_payload(value: Any) -> Any:
    """Recursively copy provider payloads while redacting obvious secret-bearing values."""

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, raw_value in value.items():
            normalized_key = str(key)
            if _is_sensitive_key(normalized_key):
                sanitized[normalized_key] = _REDACTED
                continue
            sanitized[normalized_key] = sanitize_provider_payload(raw_value)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [sanitize_provider_payload(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        return redact_sensitive_string(value)
    return value


def build_runway_submission_snapshot(
    *,
    asset_id: uuid.UUID | str | None = None,
    asset_key: str | None = None,
    asset_key_hash: str | None = None,
    task_id: uuid.UUID | str | None = None,
    task_status: str | None = None,
    asset_status: str | None = None,
    request_payload: Mapping[str, Any] | None = None,
    provider_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the persisted submission snapshot stored on a provider-job row."""

    snapshot: dict[str, Any] = {
        "provider": RUNWAY_PROVIDER,
        "status": RunwayJobStatus.SUBMITTED.value,
    }
    _set_if_present(snapshot, "asset_id", asset_id)
    _set_if_present(snapshot, "asset_key", asset_key)
    _set_if_present(snapshot, "asset_key_hash", asset_key_hash)
    _set_if_present(snapshot, "task_id", task_id)
    _set_if_present(snapshot, "task_status", task_status)
    _set_if_present(snapshot, "asset_status", asset_status)
    if request_payload is not None:
        snapshot["request_payload"] = sanitize_provider_payload(request_payload)
    if provider_payload is not None:
        snapshot["provider_payload"] = sanitize_provider_payload(provider_payload)
    return snapshot


def build_runway_poll_snapshot(
    *,
    payload: Mapping[str, Any] | None = None,
    task_status: str | None = None,
    asset_status: str | None = None,
) -> dict[str, Any]:
    """Build the latest polling snapshot for a running Runway job."""

    snapshot: dict[str, Any] = {
        "provider": RUNWAY_PROVIDER,
        "status": RunwayJobStatus.RUNNING.value,
    }
    _set_if_present(snapshot, "task_status", task_status)
    _set_if_present(snapshot, "asset_status", asset_status)
    if payload is not None:
        snapshot["provider_payload"] = sanitize_provider_payload(payload)
    return snapshot


def build_runway_result_snapshot(
    *,
    status: str | RunwayJobStatus,
    payload: Mapping[str, Any] | None = None,
    task_status: str | None = None,
    asset_status: str | None = None,
) -> dict[str, Any]:
    """Build the latest terminal snapshot for a Runway job result."""

    normalized_status = normalize_runway_job_status(status)
    snapshot: dict[str, Any] = {
        "provider": RUNWAY_PROVIDER,
        "status": normalized_status.value,
    }
    _set_if_present(snapshot, "task_status", task_status)
    _set_if_present(snapshot, "asset_status", asset_status)
    if payload is not None:
        snapshot["provider_payload"] = sanitize_provider_payload(payload)
    return snapshot


def _is_sensitive_key(key: str) -> bool:
    return any(pattern.search(key) for pattern in _SENSITIVE_KEY_PATTERNS)


def _set_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    target[key] = str(value) if isinstance(value, uuid.UUID) else value
