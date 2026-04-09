"""Sweep and reconcile stale provider jobs before they fall into limbo."""

# mypy: disable-error-code="no-any-return,untyped-decorator"

from __future__ import annotations

import uuid
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from content_lab_assets.providers.runway.jobs import RUNWAY_PROVIDER, RunwayJobStatus
from content_lab_assets.store import SQLRunwayAssetStore, StoredRunwayGeneration
from prefect.flows import flow
from prefect.tasks import task
from sqlalchemy.orm import Session, sessionmaker

from content_lab_api.db import SessionLocal
from content_lab_api.models import Asset, OutboxEvent, ProviderJob, Task
from content_lab_api.services.provider_jobs import record_provider_job_result
from content_lab_shared.settings import Settings
from content_lab_worker.actors.outbox import (
    PROVIDER_JOB_FAILURE_SIGNAL_EVENT,
    PROVIDER_JOB_REPAIR_SIGNAL_EVENT,
    build_provider_job_signal_payload,
)
from content_lab_worker.actors.provider import get_provider_sweep_threshold
from content_lab_worker.actors.runway import (
    RetryableRunwayActorError,
    TerminalRunwayActorError,
    reconcile_runway_asset,
)

from .registry import FlowDefinition

_DEFAULT_SWEEP_LIMIT = 50


@dataclass(frozen=True, slots=True)
class ProviderJobSweepCandidate:
    """A stale provider job selected for reconciliation."""

    provider_job_id: str
    org_id: str
    provider: str
    external_ref: str
    provider_job_status: str
    task_id: str | None
    task_status: str | None
    asset_id: str | None
    asset_status: str | None
    last_updated_at: str
    stale_for_seconds: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "provider_job_id": self.provider_job_id,
            "org_id": self.org_id,
            "provider": self.provider,
            "external_ref": self.external_ref,
            "provider_job_status": self.provider_job_status,
            "task_id": self.task_id,
            "task_status": self.task_status,
            "asset_id": self.asset_id,
            "asset_status": self.asset_status,
            "last_updated_at": self.last_updated_at,
            "stale_for_seconds": self.stale_for_seconds,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ProviderJobSweepCandidate:
        return cls(
            provider_job_id=str(payload["provider_job_id"]),
            org_id=str(payload["org_id"]),
            provider=str(payload["provider"]),
            external_ref=str(payload["external_ref"]),
            provider_job_status=str(payload["provider_job_status"]),
            task_id=_optional_text(payload.get("task_id")),
            task_status=_optional_text(payload.get("task_status")),
            asset_id=_optional_text(payload.get("asset_id")),
            asset_status=_optional_text(payload.get("asset_status")),
            last_updated_at=str(payload["last_updated_at"]),
            stale_for_seconds=int(payload["stale_for_seconds"]),
        )


@dataclass(frozen=True, slots=True)
class ProviderJobSweepResult:
    """Outcome from reconciling a stale provider job."""

    provider_job_id: str
    external_ref: str
    provider: str
    reconciliation_status: str
    provider_job_status: str
    task_status: str | None
    asset_status: str | None
    detail: str | None = None
    signal_event_type: str | None = None
    signal_emitted: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "provider_job_id": self.provider_job_id,
            "external_ref": self.external_ref,
            "provider": self.provider,
            "reconciliation_status": self.reconciliation_status,
            "provider_job_status": self.provider_job_status,
            "task_status": self.task_status,
            "asset_status": self.asset_status,
            "detail": self.detail,
            "signal_event_type": self.signal_event_type,
            "signal_emitted": self.signal_emitted,
        }


class ProviderJobSweeperRuntime(Protocol):
    """Runtime boundary for stale provider-job discovery and reconciliation."""

    def list_stale_jobs(
        self,
        *,
        now: datetime | None = None,
        limit: int = _DEFAULT_SWEEP_LIMIT,
    ) -> tuple[ProviderJobSweepCandidate, ...]: ...

    def reconcile_job(self, candidate: ProviderJobSweepCandidate) -> ProviderJobSweepResult: ...


class SQLProviderJobSweeperRuntime:
    """Default SQL-backed stale provider-job sweeper runtime."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session_factory = session_factory or SessionLocal
        self._settings = settings or Settings()
        self._store = SQLRunwayAssetStore(settings=self._settings)

    def list_stale_jobs(
        self,
        *,
        now: datetime | None = None,
        limit: int = _DEFAULT_SWEEP_LIMIT,
    ) -> tuple[ProviderJobSweepCandidate, ...]:
        current_time = now or datetime.now(UTC)
        candidates: list[ProviderJobSweepCandidate] = []
        with self._session_factory() as session:
            provider_jobs = (
                session.query(ProviderJob)
                .filter(ProviderJob.provider == RUNWAY_PROVIDER)
                .order_by(ProviderJob.updated_at.asc(), ProviderJob.created_at.asc())
                .all()
            )
            for provider_job in provider_jobs:
                threshold = get_provider_sweep_threshold(
                    provider=provider_job.provider,
                    status=provider_job.status,
                )
                if threshold is None:
                    continue
                last_updated_at = provider_job.updated_at or provider_job.created_at
                stale_for = current_time - last_updated_at.astimezone(UTC)
                if stale_for < threshold.max_age:
                    continue

                task = (
                    None
                    if provider_job.task_id is None
                    else session.get(Task, provider_job.task_id)
                )
                asset_id = _linked_asset_id(provider_job.metadata_)
                asset_status = None
                if asset_id is not None:
                    asset = session.get(Asset, _as_uuid(asset_id, field_name="asset_id"))
                    if asset is not None:
                        asset_status = asset.status

                candidates.append(
                    ProviderJobSweepCandidate(
                        provider_job_id=str(provider_job.id),
                        org_id=str(provider_job.org_id),
                        provider=provider_job.provider,
                        external_ref=provider_job.external_ref,
                        provider_job_status=provider_job.status,
                        task_id=None if provider_job.task_id is None else str(provider_job.task_id),
                        task_status=None if task is None else task.status,
                        asset_id=asset_id,
                        asset_status=asset_status,
                        last_updated_at=last_updated_at.astimezone(UTC).isoformat(),
                        stale_for_seconds=max(int(stale_for.total_seconds()), 0),
                    )
                )
                if len(candidates) >= limit:
                    break
        return tuple(candidates)

    def reconcile_job(self, candidate: ProviderJobSweepCandidate) -> ProviderJobSweepResult:
        if candidate.provider != RUNWAY_PROVIDER:
            return ProviderJobSweepResult(
                provider_job_id=candidate.provider_job_id,
                external_ref=candidate.external_ref,
                provider=candidate.provider,
                reconciliation_status="skipped",
                provider_job_status=candidate.provider_job_status,
                task_status=candidate.task_status,
                asset_status=candidate.asset_status,
                detail="provider is not supported by this sweeper yet",
            )

        if candidate.asset_id is None:
            return ProviderJobSweepResult(
                provider_job_id=candidate.provider_job_id,
                external_ref=candidate.external_ref,
                provider=candidate.provider,
                reconciliation_status="skipped",
                provider_job_status=candidate.provider_job_status,
                task_status=candidate.task_status,
                asset_status=candidate.asset_status,
                detail="provider job is missing linked asset metadata",
            )

        generation = self._store.load_generation(asset_id=candidate.asset_id)
        if generation.is_ready or generation.is_terminal_failure:
            return self._repair_already_finalized_job(candidate, generation)

        try:
            reconcile_runway_asset(
                asset_id=candidate.asset_id,
                external_ref=candidate.external_ref,
                store=self._store,
                settings=self._settings,
                max_polls=3,
                poll_interval_seconds=5.0,
            )
        except RetryableRunwayActorError as exc:
            return self._finalize_result(
                candidate,
                reconciliation_status="retrying",
                detail=str(exc),
                signal_event_type=PROVIDER_JOB_FAILURE_SIGNAL_EVENT,
            )
        except TerminalRunwayActorError as exc:
            return self._finalize_result(
                candidate,
                reconciliation_status="failed",
                detail=str(exc),
                signal_event_type=PROVIDER_JOB_FAILURE_SIGNAL_EVENT,
            )

        return self._finalize_result(
            candidate,
            reconciliation_status="repaired",
            signal_event_type=PROVIDER_JOB_REPAIR_SIGNAL_EVENT,
        )

    def _repair_already_finalized_job(
        self,
        candidate: ProviderJobSweepCandidate,
        generation: StoredRunwayGeneration,
    ) -> ProviderJobSweepResult:
        expected_status = _expected_runway_status(generation)
        signal_event_type = (
            PROVIDER_JOB_REPAIR_SIGNAL_EVENT
            if expected_status is RunwayJobStatus.SUCCEEDED
            else PROVIDER_JOB_FAILURE_SIGNAL_EVENT
        )

        with self._session_factory.begin() as session:
            provider_job = session.get(
                ProviderJob,
                _as_uuid(candidate.provider_job_id, field_name="provider_job_id"),
            )
            if provider_job is None:
                raise LookupError(f"Provider job {candidate.provider_job_id} was not found")

            task = None if provider_job.task_id is None else session.get(Task, provider_job.task_id)
            asset_id = _linked_asset_id(provider_job.metadata_)
            asset = (
                None
                if asset_id is None
                else session.get(Asset, _as_uuid(asset_id, field_name="asset_id"))
            )

            record_provider_job_result(
                session,
                org_id=provider_job.org_id,
                provider=provider_job.provider,
                external_ref=provider_job.external_ref,
                status=expected_status,
                payload={
                    "reconciliation": {
                        "detail": "provider job revisited after local finalization",
                        "final_asset_status": generation.asset_status,
                        "final_task_status": generation.task_status,
                    }
                },
                task_id=None if task is None else task.id,
                asset_id=None if asset is None else asset.id,
                task_status=None if task is None else task.status,
                asset_status=None if asset is None else asset.status,
            )
            emitted = self._emit_signal(
                session,
                provider_job=provider_job,
                event_type=signal_event_type,
                reconciliation_status="already_finalized",
                detail="provider job revisited after local finalization",
            )

        return self._read_result(
            candidate,
            reconciliation_status="already_finalized",
            detail="provider job revisited after local finalization",
            signal_event_type=signal_event_type,
            signal_emitted=emitted,
        )

    def _finalize_result(
        self,
        candidate: ProviderJobSweepCandidate,
        *,
        reconciliation_status: str,
        detail: str | None = None,
        signal_event_type: str | None = None,
    ) -> ProviderJobSweepResult:
        emitted = False
        if signal_event_type is not None:
            with self._session_factory.begin() as session:
                provider_job = session.get(
                    ProviderJob,
                    _as_uuid(candidate.provider_job_id, field_name="provider_job_id"),
                )
                if provider_job is None:
                    raise LookupError(f"Provider job {candidate.provider_job_id} was not found")
                emitted = self._emit_signal(
                    session,
                    provider_job=provider_job,
                    event_type=signal_event_type,
                    reconciliation_status=reconciliation_status,
                    detail=detail,
                )
        return self._read_result(
            candidate,
            reconciliation_status=reconciliation_status,
            detail=detail,
            signal_event_type=signal_event_type,
            signal_emitted=emitted,
        )

    def _read_result(
        self,
        candidate: ProviderJobSweepCandidate,
        *,
        reconciliation_status: str,
        detail: str | None,
        signal_event_type: str | None,
        signal_emitted: bool,
    ) -> ProviderJobSweepResult:
        with self._session_factory() as session:
            provider_job = session.get(
                ProviderJob,
                _as_uuid(candidate.provider_job_id, field_name="provider_job_id"),
            )
            if provider_job is None:
                raise LookupError(f"Provider job {candidate.provider_job_id} was not found")
            task = None if provider_job.task_id is None else session.get(Task, provider_job.task_id)
            asset_id = _linked_asset_id(provider_job.metadata_)
            asset = (
                None
                if asset_id is None
                else session.get(Asset, _as_uuid(asset_id, field_name="asset_id"))
            )
            return ProviderJobSweepResult(
                provider_job_id=str(provider_job.id),
                external_ref=provider_job.external_ref,
                provider=provider_job.provider,
                reconciliation_status=reconciliation_status,
                provider_job_status=provider_job.status,
                task_status=None if task is None else task.status,
                asset_status=None if asset is None else asset.status,
                detail=detail,
                signal_event_type=signal_event_type,
                signal_emitted=signal_emitted,
            )

    def _emit_signal(
        self,
        session: Session,
        *,
        provider_job: ProviderJob,
        event_type: str,
        reconciliation_status: str,
        detail: str | None,
    ) -> bool:
        task = None if provider_job.task_id is None else session.get(Task, provider_job.task_id)
        asset_id = _linked_asset_id(provider_job.metadata_)
        asset = (
            None
            if asset_id is None
            else session.get(Asset, _as_uuid(asset_id, field_name="asset_id"))
        )

        signal_key = _signal_key(
            event_type=event_type,
            reconciliation_status=reconciliation_status,
            provider_job_status=provider_job.status,
            task_status=None if task is None else task.status,
            asset_status=None if asset is None else asset.status,
        )
        metadata = dict(provider_job.metadata_ or {})
        reconciliation = _mapping(metadata.get("reconciliation"))
        signals = _mapping(reconciliation.get("signals"))
        existing_signal = _mapping(signals.get(event_type))
        if existing_signal.get("key") == signal_key:
            reconciliation["last_reconciled_at"] = datetime.now(UTC).isoformat()
            reconciliation["last_outcome"] = reconciliation_status
            metadata["reconciliation"] = reconciliation
            provider_job.metadata_ = metadata
            return False

        payload = build_provider_job_signal_payload(
            provider_job_id=str(provider_job.id),
            provider=provider_job.provider,
            external_ref=provider_job.external_ref,
            reconciliation_status=reconciliation_status,
            provider_job_status=provider_job.status,
            task_status=None if task is None else task.status,
            asset_status=None if asset is None else asset.status,
            asset_id=None if asset is None else str(asset.id),
            task_id=None if task is None else str(task.id),
            detail=detail,
        )
        session.add(
            OutboxEvent(
                org_id=provider_job.org_id,
                aggregate_type="provider_job",
                aggregate_id=str(provider_job.id),
                event_type=event_type,
                payload=payload,
            )
        )
        signals[event_type] = {
            "detail": detail,
            "emitted_at": datetime.now(UTC).isoformat(),
            "key": signal_key,
        }
        reconciliation["signals"] = signals
        reconciliation["last_reconciled_at"] = datetime.now(UTC).isoformat()
        reconciliation["last_outcome"] = reconciliation_status
        metadata["reconciliation"] = reconciliation
        provider_job.metadata_ = metadata
        return True


def build_provider_job_sweeper_runtime() -> ProviderJobSweeperRuntime:
    """Construct the default runtime for stale provider-job reconciliation."""

    return SQLProviderJobSweeperRuntime()


@task
def find_stale_provider_jobs(limit: int) -> list[dict[str, Any]]:
    """Find non-terminal provider jobs whose age exceeds their sweep threshold."""

    runtime = build_provider_job_sweeper_runtime()
    return [candidate.to_payload() for candidate in runtime.list_stale_jobs(limit=limit)]


@task
def reconcile_stale_provider_jobs(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconcile each stale provider job and return stable result payloads."""

    runtime = build_provider_job_sweeper_runtime()
    results: list[dict[str, Any]] = []
    for candidate_payload in candidates:
        candidate = ProviderJobSweepCandidate.from_payload(candidate_payload)
        results.append(runtime.reconcile_job(candidate).to_payload())
    return results


@flow(name="provider_job_sweeper")
def provider_job_sweeper(limit: int = _DEFAULT_SWEEP_LIMIT) -> dict[str, Any]:
    """Sweep stale provider jobs and reconcile their persisted lifecycle state."""

    candidate_payloads = find_stale_provider_jobs(limit)
    result_payloads = reconcile_stale_provider_jobs(candidate_payloads)

    counts = {
        "stale": len(candidate_payloads),
        "repaired": 0,
        "failed": 0,
        "retrying": 0,
        "already_finalized": 0,
        "skipped": 0,
        "signals_emitted": 0,
    }
    for payload in result_payloads:
        status = str(payload["reconciliation_status"])
        if status in counts:
            counts[status] += 1
        if bool(payload.get("signal_emitted")):
            counts["signals_emitted"] += 1

    return {
        "status": "completed",
        "counts": counts,
        "candidates": candidate_payloads,
        "results": result_payloads,
    }


def build_provider_job_sweeper_kwargs(_args: Namespace) -> dict[str, object]:
    """Map CLI arguments onto the flow signature."""

    return {}


FLOW_DEFINITION = FlowDefinition(
    name="provider_job_sweeper",
    description="Sweep stale provider jobs and reconcile stuck or delayed external work.",
    entrypoint=provider_job_sweeper,
    build_kwargs=build_provider_job_sweeper_kwargs,
)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _linked_asset_id(metadata: Mapping[str, Any] | None) -> str | None:
    links = _mapping(_mapping(metadata).get("links"))
    return _optional_text(links.get("asset_id"))


def _signal_key(
    *,
    event_type: str,
    reconciliation_status: str,
    provider_job_status: str,
    task_status: str | None,
    asset_status: str | None,
) -> str:
    return "|".join(
        (
            event_type,
            reconciliation_status,
            provider_job_status,
            task_status or "",
            asset_status or "",
        )
    )


def _expected_runway_status(generation: StoredRunwayGeneration) -> RunwayJobStatus:
    if generation.is_ready:
        return RunwayJobStatus.SUCCEEDED

    task_result = _mapping(generation.task_result)
    provider_job_payload = _mapping(task_result.get("provider_job"))
    provider_job_status = _optional_text(provider_job_payload.get("status"))
    if provider_job_status is not None:
        normalized = provider_job_status.lower()
        if normalized == RunwayJobStatus.SUCCEEDED.value:
            return RunwayJobStatus.SUCCEEDED
        if normalized == RunwayJobStatus.CANCELLED.value:
            return RunwayJobStatus.CANCELLED
        if normalized == RunwayJobStatus.FAILED.value:
            return RunwayJobStatus.FAILED

    phase = (_optional_text(task_result.get("phase")) or "").lower()
    if phase in {"download", "ready"}:
        return RunwayJobStatus.SUCCEEDED
    return RunwayJobStatus.FAILED


def _as_uuid(value: str, *, field_name: str) -> uuid.UUID:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return uuid.UUID(normalized)


__all__ = [
    "FLOW_DEFINITION",
    "ProviderJobSweepCandidate",
    "ProviderJobSweepResult",
    "ProviderJobSweeperRuntime",
    "SQLProviderJobSweeperRuntime",
    "build_provider_job_sweeper_runtime",
    "provider_job_sweeper",
]
