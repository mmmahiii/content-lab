"""Schema-aligned, read-only snapshot of operational Postgres rows.

Column selections mirror the SQLAlchemy models under ``content_lab_api.models`` so
repo-local diagnostics stay aligned with Alembic migrations.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from content_lab_api.models.asset import Asset
from content_lab_api.models.outbox import OutboxEvent
from content_lab_api.models.provider_job import ProviderJob
from content_lab_api.models.reel import Reel
from content_lab_api.models.run import Run
from content_lab_api.models.run_asset import RunAsset
from content_lab_api.models.task import Task

SCHEMA_TABLES_PHASE1: frozenset[str] = frozenset(
    {
        "assets",
        "orgs",
        "outbox_events",
        "provider_jobs",
        "reels",
        "run_assets",
        "runs",
        "tasks",
    }
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    return value


def _row_mapping(row: Any) -> dict[str, Any]:
    return {k: _json_safe(v) for k, v in row._mapping.items()}


def _try_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _reel_ids_from_runs(runs: Sequence[Run]) -> list[uuid.UUID]:
    ordered: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for run in runs:
        params = run.input_params if isinstance(run.input_params, Mapping) else {}
        rid = _try_uuid(params.get("reel_id"))
        if rid is not None and rid not in seen:
            seen.add(rid)
            ordered.append(rid)
        meta = run.run_metadata if isinstance(run.run_metadata, Mapping) else {}
        target = meta.get("target")
        if isinstance(target, Mapping):
            rid = _try_uuid(target.get("reel_id"))
            if rid is not None and rid not in seen:
                seen.add(rid)
                ordered.append(rid)
    return ordered


def _package_hints(output_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not output_payload:
        return {"output_payload_keys": [], "package_keys": None}
    keys = sorted(str(k) for k in output_payload)
    pkg = output_payload.get("package")
    package_keys = sorted(str(k) for k in pkg) if isinstance(pkg, Mapping) else None
    return {"output_payload_keys": keys, "package_keys": package_keys}


def build_runtime_db_snapshot(
    db: Session,
    *,
    org_id: uuid.UUID | None,
    run_id: uuid.UUID | None,
    limit_runs: int = 5,
    limit_tasks: int = 100,
    limit_outbox: int = 100,
    limit_provider_jobs: int = 50,
    limit_assets: int = 50,
    limit_run_assets: int = 100,
) -> dict[str, Any]:
    """Return a JSON-serialisable dict of recent operational rows (read-only)."""

    resolved_org_id = org_id
    if run_id is not None:
        run_row = db.get(Run, run_id)
        if run_row is None:
            raise ValueError(f"Run not found: {run_id}")
        if resolved_org_id is not None and run_row.org_id != resolved_org_id:
            raise ValueError("run.org_id does not match provided org_id")
        resolved_org_id = run_row.org_id

    if resolved_org_id is None:
        raise ValueError("Provide org_id and/or an existing run_id")

    if run_id is not None:
        runs_stmt = select(Run).where(Run.id == run_id)
    else:
        runs_stmt = (
            select(Run)
            .where(Run.org_id == resolved_org_id)
            .order_by(Run.created_at.desc())
            .limit(max(1, min(limit_runs, 50)))
        )
    run_entities = list(db.scalars(runs_stmt).unique().all())
    run_ids = [r.id for r in run_entities]
    reel_ids = _reel_ids_from_runs(run_entities)

    runs_out = []
    for r in run_entities:
        runs_out.append(
            {
                "id": str(r.id),
                "org_id": str(r.org_id),
                "workflow_key": r.workflow_key,
                "flow_trigger": r.flow_trigger,
                "status": r.status,
                "idempotency_key": r.idempotency_key,
                "external_ref": r.external_ref,
                "started_at": _json_safe(r.started_at),
                "finished_at": _json_safe(r.finished_at),
                "created_at": _json_safe(r.created_at),
                "updated_at": _json_safe(r.updated_at),
                "package_hints": _package_hints(r.output_payload),
            }
        )

    task_rows: list[dict[str, Any]] = []
    if run_ids:
        tasks_stmt = (
            select(Task)
            .where(Task.org_id == resolved_org_id, Task.run_id.in_(run_ids))
            .order_by(Task.created_at.asc(), Task.task_type.asc())
            .limit(max(1, min(limit_tasks, 500)))
        )
        for t in db.scalars(tasks_stmt).unique().all():
            task_rows.append(
                {
                    "id": str(t.id),
                    "org_id": str(t.org_id),
                    "task_type": t.task_type,
                    "idempotency_key": t.idempotency_key,
                    "status": t.status,
                    "run_id": str(t.run_id) if t.run_id else None,
                    "payload": _json_safe(t.payload),
                    "result": _json_safe(t.result),
                    "created_at": _json_safe(t.created_at),
                    "updated_at": _json_safe(t.updated_at),
                }
            )

    outbox_rows: list[dict[str, Any]] = []
    if run_ids:
        aggregate_ids = [str(rid) for rid in run_ids]
        o_stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.org_id == resolved_org_id,
                OutboxEvent.aggregate_id.in_(aggregate_ids),
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(max(1, min(limit_outbox, 500)))
        )
        for ev in db.scalars(o_stmt).unique().all():
            outbox_rows.append(
                {
                    "id": str(ev.id),
                    "org_id": str(ev.org_id),
                    "aggregate_type": ev.aggregate_type,
                    "aggregate_id": ev.aggregate_id,
                    "event_type": ev.event_type,
                    "delivery_status": ev.delivery_status,
                    "attempt_count": ev.attempt_count,
                    "next_attempt_at": _json_safe(ev.next_attempt_at),
                    "dispatched_at": _json_safe(ev.dispatched_at),
                    "created_at": _json_safe(ev.created_at),
                    "payload": _json_safe(ev.payload),
                }
            )

    pj_stmt = (
        select(ProviderJob)
        .where(ProviderJob.org_id == resolved_org_id)
        .order_by(ProviderJob.created_at.desc())
        .limit(max(1, min(limit_provider_jobs, 200)))
    )
    provider_jobs: list[dict[str, Any]] = []
    for pj in db.scalars(pj_stmt).unique().all():
        provider_jobs.append(
            {
                "id": str(pj.id),
                "org_id": str(pj.org_id),
                "provider": pj.provider,
                "external_ref": pj.external_ref,
                "task_id": str(pj.task_id) if pj.task_id else None,
                "status": pj.status,
                "metadata": _json_safe(pj.metadata_),
                "created_at": _json_safe(pj.created_at),
                "updated_at": _json_safe(pj.updated_at),
            }
        )

    asset_stmt = (
        select(
            Asset.id,
            Asset.org_id,
            Asset.asset_class,
            Asset.storage_uri,
            Asset.source,
            Asset.asset_key,
            Asset.status,
            Asset.created_at,
            Asset.family_id,
        )
        .where(Asset.org_id == resolved_org_id)
        .order_by(Asset.created_at.desc())
        .limit(max(1, min(limit_assets, 200)))
    )
    assets = [_row_mapping(row) for row in db.execute(asset_stmt)]

    run_assets: list[dict[str, Any]] = []
    if run_ids:
        ra_stmt = (
            select(RunAsset)
            .where(RunAsset.org_id == resolved_org_id, RunAsset.run_id.in_(run_ids))
            .order_by(RunAsset.run_id.asc())
            .limit(max(1, min(limit_run_assets, 500)))
        )
        for ra in db.scalars(ra_stmt).unique().all():
            run_assets.append(
                {
                    "id": str(ra.id),
                    "org_id": str(ra.org_id),
                    "run_id": str(ra.run_id),
                    "asset_id": str(ra.asset_id),
                    "asset_role": ra.asset_role,
                }
            )

    reels_out: list[dict[str, Any]] = []
    if reel_ids:
        reel_stmt = select(Reel).where(
            Reel.org_id == resolved_org_id,
            Reel.id.in_(reel_ids),
        )
        for reel in db.scalars(reel_stmt).unique().all():
            reels_out.append(
                {
                    "id": str(reel.id),
                    "org_id": str(reel.org_id),
                    "reel_family_id": str(reel.reel_family_id),
                    "origin": reel.origin,
                    "status": reel.status,
                    "variant_label": reel.variant_label,
                    "external_reel_id": reel.external_reel_id,
                    "created_at": _json_safe(reel.created_at),
                    "updated_at": _json_safe(reel.updated_at),
                }
            )

    return {
        "meta": {
            "org_id": str(resolved_org_id),
            "run_id_filter": str(run_id) if run_id else None,
            "schema_tables_phase1": sorted(SCHEMA_TABLES_PHASE1),
            "note": (
                "Packages are not a separate table; hints come from runs.output_payload "
                "and package artifacts are assets linked via run_assets."
            ),
        },
        "runs": runs_out,
        "tasks": task_rows,
        "outbox_events": outbox_rows,
        "provider_jobs": provider_jobs,
        "assets": assets,
        "run_assets": run_assets,
        "reels": reels_out,
    }
