"""Provider-job persistence helpers for external submission, polling, and final results."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from content_lab_api.models.provider_job import ProviderJob
from content_lab_assets.canonicalise import normalize_identifier
from content_lab_assets.providers.runway.jobs import (
    RUNWAY_PROVIDER,
    RunwayJobStatus,
    build_runway_poll_snapshot,
    build_runway_result_snapshot,
    build_runway_submission_snapshot,
    normalize_runway_job_status,
)

_PROVIDER_JOB_EXTERNAL_REF_CONSTRAINT = "uq_provider_jobs_provider_external_ref"


def get_provider_job_by_external_ref(
    db: Session,
    *,
    provider: str,
    external_ref: str,
) -> ProviderJob | None:
    """Return an existing provider-job row by its provider/external-ref pair."""

    return (
        db.query(ProviderJob)
        .filter(
            ProviderJob.provider == _normalize_provider(provider),
            ProviderJob.external_ref == _normalize_external_ref(external_ref),
        )
        .one_or_none()
    )


def record_provider_job_submission(
    db: Session,
    *,
    org_id: uuid.UUID | str,
    task_id: uuid.UUID | str | None,
    asset_id: uuid.UUID | str | None,
    asset_key: str | None,
    asset_key_hash: str | None,
    request_payload: Mapping[str, Any] | None,
    provider_payload: Mapping[str, Any],
    task_status: str | None = None,
    asset_status: str | None = None,
) -> ProviderJob:
    """Create or update the durable provider-job row for a submission request."""

    provider = _provider_from_payload(provider_payload)
    external_ref = _external_ref_from_payload(provider_payload)
    snapshot = build_runway_submission_snapshot(
        asset_id=asset_id,
        asset_key=asset_key,
        asset_key_hash=asset_key_hash,
        task_id=task_id,
        task_status=task_status,
        asset_status=asset_status,
        request_payload=request_payload,
        provider_payload=provider_payload,
    )
    return _upsert_provider_job(
        db,
        org_id=org_id,
        provider=provider,
        external_ref=external_ref,
        status=RunwayJobStatus.SUBMITTED,
        task_id=task_id,
        asset_id=asset_id,
        snapshot_key="submission",
        snapshot=snapshot,
    )


def record_provider_job_poll(
    db: Session,
    *,
    org_id: uuid.UUID | str,
    provider: str,
    external_ref: str,
    payload: Mapping[str, Any] | None = None,
    task_id: uuid.UUID | str | None = None,
    asset_id: uuid.UUID | str | None = None,
    task_status: str | None = None,
    asset_status: str | None = None,
) -> ProviderJob:
    """Persist the latest polling snapshot for a running provider job."""

    snapshot = build_runway_poll_snapshot(
        payload=payload,
        task_status=task_status,
        asset_status=asset_status,
    )
    return _upsert_provider_job(
        db,
        org_id=org_id,
        provider=provider,
        external_ref=external_ref,
        status=RunwayJobStatus.RUNNING,
        task_id=task_id,
        asset_id=asset_id,
        snapshot_key="poll",
        snapshot=snapshot,
    )


def record_provider_job_result(
    db: Session,
    *,
    org_id: uuid.UUID | str,
    provider: str,
    external_ref: str,
    status: str | RunwayJobStatus,
    payload: Mapping[str, Any] | None = None,
    task_id: uuid.UUID | str | None = None,
    asset_id: uuid.UUID | str | None = None,
    task_status: str | None = None,
    asset_status: str | None = None,
) -> ProviderJob:
    """Persist the final provider snapshot for a succeeded, failed, or cancelled job."""

    normalized_status = normalize_runway_job_status(status)
    snapshot = build_runway_result_snapshot(
        status=normalized_status,
        payload=payload,
        task_status=task_status,
        asset_status=asset_status,
    )
    return _upsert_provider_job(
        db,
        org_id=org_id,
        provider=provider,
        external_ref=external_ref,
        status=normalized_status,
        task_id=task_id,
        asset_id=asset_id,
        snapshot_key="result",
        snapshot=snapshot,
    )


def _upsert_provider_job(
    db: Session,
    *,
    org_id: uuid.UUID | str,
    provider: str,
    external_ref: str,
    status: RunwayJobStatus,
    snapshot_key: str,
    snapshot: Mapping[str, Any],
    task_id: uuid.UUID | str | None = None,
    asset_id: uuid.UUID | str | None = None,
) -> ProviderJob:
    normalized_provider = _normalize_provider(provider)
    normalized_external_ref = _normalize_external_ref(external_ref)
    normalized_task_id = _as_optional_uuid(task_id, field_name="task_id")
    normalized_asset_id = _as_optional_uuid(asset_id, field_name="asset_id")
    existing = get_provider_job_by_external_ref(
        db,
        provider=normalized_provider,
        external_ref=normalized_external_ref,
    )
    if existing is not None:
        return _apply_provider_job_update(
            existing,
            status=status,
            task_id=normalized_task_id,
            asset_id=normalized_asset_id,
            snapshot_key=snapshot_key,
            snapshot=snapshot,
        )

    job = ProviderJob(
        org_id=_as_uuid(org_id, field_name="org_id"),
        provider=normalized_provider,
        external_ref=normalized_external_ref,
        task_id=normalized_task_id,
        status=status.value,
        metadata_=_build_metadata(
            provider=normalized_provider,
            external_ref=normalized_external_ref,
            task_id=normalized_task_id,
            asset_id=normalized_asset_id,
            snapshot_key=snapshot_key,
            snapshot=snapshot,
        ),
    )

    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError as exc:
        if _PROVIDER_JOB_EXTERNAL_REF_CONSTRAINT not in _error_message(exc):
            raise
        existing = get_provider_job_by_external_ref(
            db,
            provider=normalized_provider,
            external_ref=normalized_external_ref,
        )
        if existing is None:
            raise
        return _apply_provider_job_update(
            existing,
            status=status,
            task_id=normalized_task_id,
            asset_id=normalized_asset_id,
            snapshot_key=snapshot_key,
            snapshot=snapshot,
        )

    return job


def _apply_provider_job_update(
    job: ProviderJob,
    *,
    status: RunwayJobStatus,
    task_id: uuid.UUID | None,
    asset_id: uuid.UUID | None,
    snapshot_key: str,
    snapshot: Mapping[str, Any],
) -> ProviderJob:
    job.status = status.value
    if task_id is not None:
        job.task_id = task_id
    job.metadata_ = _merge_metadata(
        job.metadata_,
        _build_metadata(
            provider=job.provider,
            external_ref=job.external_ref,
            task_id=task_id,
            asset_id=asset_id,
            snapshot_key=snapshot_key,
            snapshot=snapshot,
        ),
    )
    return job


def _build_metadata(
    *,
    provider: str,
    external_ref: str,
    task_id: uuid.UUID | None,
    asset_id: uuid.UUID | None,
    snapshot_key: str,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    status = str(snapshot.get("status", ""))
    task_status = snapshot.get("task_status")
    asset_status = snapshot.get("asset_status")
    return {
        "links": {
            **({} if task_id is None else {"task_id": str(task_id)}),
            **({} if asset_id is None else {"asset_id": str(asset_id)}),
        },
        "provider_ref": {
            "provider": provider,
            "external_ref": external_ref,
        },
        "snapshots": {
            snapshot_key: dict(snapshot),
        },
        "history": [
            {
                "status": status,
                "snapshot": snapshot_key,
                "external_ref": external_ref,
                "recorded_at": datetime.now(UTC).isoformat(),
                **({} if task_status is None else {"task_status": task_status}),
                **({} if asset_status is None else {"asset_status": asset_status}),
            }
        ],
    }


def _merge_metadata(
    base: Mapping[str, Any] | None,
    patch: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(base or {})
    if not patch:
        return merged

    for key, value in patch.items():
        existing = merged.get(key)
        if key == "history":
            merged[key] = [*list(existing or []), *list(value)]
            continue
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_metadata(existing, value)
            continue
        merged[key] = value
    return merged


def _provider_from_payload(payload: Mapping[str, Any]) -> str:
    provider = payload.get("provider", RUNWAY_PROVIDER)
    if not isinstance(provider, str):
        raise TypeError("provider payload field 'provider' must be a string")
    return provider


def _external_ref_from_payload(payload: Mapping[str, Any]) -> str:
    external_ref = payload.get("external_ref")
    if not isinstance(external_ref, str):
        raise TypeError("provider payload field 'external_ref' must be a string")
    return external_ref


def _normalize_provider(provider: str) -> str:
    return str(normalize_identifier(provider, field_name="provider"))


def _normalize_external_ref(external_ref: str) -> str:
    normalized = external_ref.strip()
    if not normalized:
        raise ValueError("external_ref must not be blank")
    return normalized


def _as_uuid(value: uuid.UUID | str, *, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return uuid.UUID(normalized)


def _as_optional_uuid(
    value: uuid.UUID | str | None,
    *,
    field_name: str,
) -> uuid.UUID | None:
    if value is None:
        return None
    return _as_uuid(value, field_name=field_name)


def _error_message(exc: IntegrityError) -> str:
    return str(exc.orig if exc.orig is not None else exc)
