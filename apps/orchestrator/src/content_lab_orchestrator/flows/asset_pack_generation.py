"""Prefect orchestration for reusable asset pack planning and generation."""

# mypy: disable-error-code="no-any-return,untyped-decorator"

from __future__ import annotations

import uuid
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from prefect.flows import flow
from prefect.tasks import task
from sqlalchemy.orm import Session, sessionmaker

from content_lab_api.db import SessionLocal
from content_lab_api.models import AssetPack, OutboxEvent, Run, Task
from content_lab_api.schemas.asset_packs import (
    ApprovedAssetPackGenerateRequest,
    AssetPackCreate,
    AssetPackOut,
    AssetPackPlanRequest,
    AssetPackReviewDecisionRequest,
)
from content_lab_api.schemas.runs import FlowTrigger
from content_lab_api.services import (
    approve_asset_pack_plan,
    create_asset_pack,
    create_run_row,
    ensure_task_row,
    generate_approved_asset_pack,
    plan_existing_asset_pack,
    refresh_asset_pack_readiness,
)
from content_lab_orchestrator.correlation import orchestrator_service_context
from content_lab_runs import RunRowSpec, RunStatus, TaskRowSpec, TaskStatus

from .registry import FlowDefinition

_WORKFLOW_KEY = "generate_asset_pack"
_EVENT_TYPE = "asset_pack.generation.completed"


class AssetPackGenerationRuntime(Protocol):
    """Persistence boundary for the asset-pack generation flow."""

    def start_run(self, request_payload: Mapping[str, Any]) -> dict[str, Any]: ...

    def create_pack(self, request_payload: Mapping[str, Any]) -> dict[str, Any]: ...

    def create_plan(
        self,
        request_payload: Mapping[str, Any],
        pack_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def approve_or_wait(
        self,
        request_payload: Mapping[str, Any],
        plan_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def resolve_existing_assets(
        self,
        request_payload: Mapping[str, Any],
        plan_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def generate_missing_assets(
        self,
        request_payload: Mapping[str, Any],
        approval_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def register_assets(
        self,
        request_payload: Mapping[str, Any],
        generation_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def mark_pack_ready(
        self,
        request_payload: Mapping[str, Any],
        registration_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def emit_notification(self, summary: Mapping[str, Any]) -> dict[str, Any]: ...

    def mark_failed(
        self,
        request_payload: Mapping[str, Any],
        *,
        failed_step: str,
        error_message: str,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class _RequestState:
    actor: str = "orchestrator"
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class _RequestUrl:
    path: str


@dataclass(frozen=True, slots=True)
class _OrchestratorRequest:
    state: _RequestState
    method: str
    url: _RequestUrl


def _request(path: str) -> Request:
    return cast(
        Request,
        _OrchestratorRequest(
            state=_RequestState(request_id=f"orchestrator:{uuid.uuid4()}"),
            method="ORCHESTRATOR",
            url=_RequestUrl(path=path),
        ),
    )


class SQLAssetPackGenerationRuntime:
    """SQL-backed implementation used by real orchestrator runs."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or SessionLocal

    def start_run(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        org_id = _as_uuid(request_payload["org_id"], field_name="org_id")
        run_id = _optional_text(request_payload.get("run_id"))
        idempotency_key = _optional_text(request_payload.get("idempotency_key")) or (
            f"{_WORKFLOW_KEY}:{request_payload.get('asset_pack_id') or request_payload['name']}:"
            f"{request_payload['niche']}"
        )
        with self._session_factory() as session:
            if run_id is not None:
                run = session.get(Run, _as_uuid(run_id, field_name="run_id"))
                if run is None:
                    raise LookupError(f"Run {run_id} was not found")
                run.status = RunStatus.RUNNING.value
            else:
                run = create_run_row(
                    session,
                    spec=RunRowSpec(
                        org_id=org_id,
                        workflow_key=_WORKFLOW_KEY,
                        flow_trigger=FlowTrigger.MANUAL.value,
                        idempotency_key=idempotency_key,
                        status=RunStatus.RUNNING,
                        input_params=dict(request_payload),
                        run_metadata={"orchestrator_flow": _WORKFLOW_KEY},
                    ),
                )
            run.started_at = run.started_at or datetime.now(UTC)
            session.commit()
            session.refresh(run)
            return {"run_id": str(run.id), "workflow_key": run.workflow_key, "status": run.status}

    def create_pack(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        if request_payload.get("asset_pack_id"):
            return {
                "asset_pack": {"id": str(request_payload["asset_pack_id"])},
                "created": False,
            }
        with self._step(request_payload, "create_pack") as (session, task_row):
            body = AssetPackCreate(
                name=str(request_payload["name"]),
                niche=str(request_payload["niche"]),
                purpose=_optional_text(request_payload.get("purpose")),
                target_audience=_optional_text(request_payload.get("target_audience")),
                requested_asset_count=int(request_payload["requested_asset_count"]),
                asset_mix_requested_json=_mapping_or_none(request_payload.get("asset_mix")),
            )
            pack = create_asset_pack(
                session,
                _request("/orchestrator/asset-packs"),
                org_id=_as_uuid(request_payload["org_id"], field_name="org_id"),
                body=body,
            )
            result = {"asset_pack": pack.model_dump(mode="json"), "created": True}
            task_row.result = result
            return result

    def create_plan(
        self,
        request_payload: Mapping[str, Any],
        pack_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        asset_pack_id = _asset_pack_id(pack_payload)
        with self._step(request_payload, "create_plan") as (session, task_row):
            body = AssetPackPlanRequest(
                name=_optional_text(request_payload.get("name")),
                niche=str(request_payload["niche"]),
                requested_asset_count=int(request_payload["requested_asset_count"]),
                asset_mix=_mapping_or_none(request_payload.get("asset_mix")),
                target_reel_types=_list_of_text(request_payload.get("target_reel_types")),
                style_persona_constraints=_mapping(request_payload.get("style_persona_constraints")),
                purpose=_optional_text(request_payload.get("purpose")),
                target_audience=_optional_text(request_payload.get("target_audience")),
            )
            plan = plan_existing_asset_pack(
                session,
                _request(f"/orchestrator/asset-packs/{asset_pack_id}/plan"),
                org_id=_as_uuid(request_payload["org_id"], field_name="org_id"),
                asset_pack_id=_as_uuid(asset_pack_id, field_name="asset_pack_id"),
                body=body,
            )
            result = plan.model_dump(mode="json")
            task_row.result = result
            return result

    def approve_or_wait(
        self,
        request_payload: Mapping[str, Any],
        plan_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        asset_pack_id = _asset_pack_id(plan_payload)
        if not bool(request_payload.get("auto_approve", True)):
            return {
                "asset_pack_id": asset_pack_id,
                "status": "awaiting_approval",
                "auto_approved": False,
            }
        with self._step(request_payload, "approve_plan") as (session, task_row):
            pack = approve_asset_pack_plan(
                session,
                _request(f"/orchestrator/asset-packs/{asset_pack_id}/approve"),
                org_id=_as_uuid(request_payload["org_id"], field_name="org_id"),
                asset_pack_id=_as_uuid(asset_pack_id, field_name="asset_pack_id"),
                body=AssetPackReviewDecisionRequest(
                    note="Auto-approved by generate_asset_pack flow.",
                    metadata={"auto_approved_by": "orchestrator"},
                ),
            )
            result = {
                "asset_pack": pack.model_dump(mode="json"),
                "asset_pack_id": str(pack.id),
                "status": pack.status,
                "auto_approved": True,
            }
            task_row.result = result
            return result

    def resolve_existing_assets(
        self,
        request_payload: Mapping[str, Any],
        plan_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        summary = _mapping(plan_payload.get("planning_resolution_summary"))
        result = {
            "asset_pack_id": _asset_pack_id(plan_payload),
            "resolution_summary": summary,
            "ready_assets": int(summary.get("ready_assets") or 0),
        }
        self._record_instant_step(request_payload, "resolve_existing_assets", result)
        return result

    def generate_missing_assets(
        self,
        request_payload: Mapping[str, Any],
        approval_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        asset_pack_id = _required_text(approval_payload.get("asset_pack_id"), "asset_pack_id")
        with self._step(request_payload, "generate_missing_assets") as (session, task_row):
            batch = generate_approved_asset_pack(
                session,
                _request(f"/orchestrator/asset-packs/{asset_pack_id}/generate"),
                org_id=_as_uuid(request_payload["org_id"], field_name="org_id"),
                asset_pack_id=_as_uuid(asset_pack_id, field_name="asset_pack_id"),
                body=ApprovedAssetPackGenerateRequest(
                    provider=str(request_payload.get("provider") or "runway"),
                    model=str(request_payload.get("model") or "gen4.5"),
                    asset_class=str(request_payload.get("asset_class") or "component"),
                    negative_prompt=_optional_text(request_payload.get("negative_prompt")),
                    seed=_optional_int(request_payload.get("seed")),
                    duration_seconds=_optional_float(request_payload.get("duration_seconds")),
                    fps=_optional_int(request_payload.get("fps")),
                    ratio=_optional_text(request_payload.get("ratio")) or "9:16",
                    motion=_mapping(request_payload.get("motion")),
                    allow_existing_reuse=bool(request_payload.get("allow_existing_reuse", True)),
                    ready_threshold=_optional_int(request_payload.get("ready_threshold")),
                ),
            )
            result = batch.model_dump(mode="json")
            task_row.result = {
                "asset_pack_id": asset_pack_id,
                "resolution_summary": result.get("resolution_summary", {}),
                "generation_decision_count": len(result.get("generation_decisions") or []),
            }
            return result

    def register_assets(
        self,
        request_payload: Mapping[str, Any],
        generation_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        asset_pack_id = _asset_pack_id(generation_payload)
        with self._step(request_payload, "register_assets") as (session, task_row):
            pack = _load_pack(session, request_payload=request_payload, asset_pack_id=asset_pack_id)
            refresh_asset_pack_readiness(
                session,
                asset_pack=pack,
                ready_threshold=_optional_int(request_payload.get("ready_threshold")),
            )
            session.commit()
            session.refresh(pack)
            result = {
                "asset_pack_id": str(pack.id),
                "status": pack.status,
                "resolution_summary": _mapping(generation_payload.get("resolution_summary")),
            }
            task_row.result = result
            return result

    def mark_pack_ready(
        self,
        request_payload: Mapping[str, Any],
        registration_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        asset_pack_id = _required_text(registration_payload.get("asset_pack_id"), "asset_pack_id")
        with self._session_factory() as session:
            pack = _load_pack(session, request_payload=request_payload, asset_pack_id=asset_pack_id)
            run = _load_run(session, request_payload)
            summary = {
                "run_id": str(run.id),
                "workflow_key": _WORKFLOW_KEY,
                "run_status": RunStatus.SUCCEEDED.value,
                "asset_pack_id": str(pack.id),
                "asset_pack_status": pack.status,
                "resolution_summary": _mapping(registration_payload.get("resolution_summary")),
                "awaiting_approval": bool(registration_payload.get("awaiting_approval", False)),
            }
            run.status = RunStatus.SUCCEEDED.value
            run.finished_at = datetime.now(UTC)
            run.output_payload = summary
            session.commit()
            return summary

    def emit_notification(self, summary: Mapping[str, Any]) -> dict[str, Any]:
        org_id = _optional_text(summary.get("org_id"))
        with self._session_factory() as session:
            run = session.get(Run, _as_uuid(summary["run_id"], field_name="run_id"))
            if run is None:
                raise LookupError(f"Run {summary['run_id']} was not found")
            event = OutboxEvent(
                org_id=run.org_id if org_id is None else _as_uuid(org_id, field_name="org_id"),
                aggregate_type="asset_pack",
                aggregate_id=str(summary["asset_pack_id"]),
                event_type=_EVENT_TYPE,
                payload=dict(summary),
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            return {"event_id": str(event.id), "event_type": event.event_type, "emitted": True}

    def mark_failed(
        self,
        request_payload: Mapping[str, Any],
        *,
        failed_step: str,
        error_message: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            run = _load_run(session, request_payload)
            summary = {
                "run_id": str(run.id),
                "workflow_key": _WORKFLOW_KEY,
                "run_status": RunStatus.FAILED.value,
                "failed_step": failed_step,
                "error_message": error_message,
            }
            run.status = RunStatus.FAILED.value
            run.finished_at = datetime.now(UTC)
            run.output_payload = summary
            session.commit()
            return summary

    def _record_instant_step(
        self,
        request_payload: Mapping[str, Any],
        task_type: str,
        result: dict[str, Any],
    ) -> None:
        with self._step(request_payload, task_type) as (_session, task_row):
            task_row.result = result

    def _step(self, request_payload: Mapping[str, Any], task_type: str) -> _TaskStep:
        return _TaskStep(self._session_factory, request_payload=request_payload, task_type=task_type)


class _TaskStep:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        request_payload: Mapping[str, Any],
        task_type: str,
    ) -> None:
        self._session_factory = session_factory
        self._request_payload = request_payload
        self._task_type = task_type
        self._session: Session | None = None
        self._task: Task | None = None

    def __enter__(self) -> tuple[Session, Task]:
        session = self._session_factory()
        run = _load_run(session, self._request_payload)
        task_result = ensure_task_row(
            session,
            spec=TaskRowSpec(
                org_id=run.org_id,
                task_type=f"{_WORKFLOW_KEY}.{self._task_type}",
                idempotency_key=f"{_WORKFLOW_KEY}:{run.id}:{self._task_type}",
                status=TaskStatus.RUNNING,
                run_id=run.id,
                payload=dict(self._request_payload),
            ),
        )
        task_row = task_result.record
        task_row.status = TaskStatus.RUNNING.value
        session.commit()
        self._session = session
        self._task = task_row
        return session, task_row

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._session is None or self._task is None:
            return
        if exc is None:
            self._task.status = TaskStatus.SUCCEEDED.value
        else:
            self._task.status = TaskStatus.FAILED.value
            self._task.result = {"error": str(exc)}
        self._session.commit()
        self._session.close()


def build_asset_pack_generation_runtime() -> AssetPackGenerationRuntime:
    return SQLAssetPackGenerationRuntime()


@task
def validate_asset_pack_generation_request(request_payload: dict[str, Any]) -> dict[str, Any]:
    _as_uuid(request_payload["org_id"], field_name="org_id")
    if not request_payload.get("asset_pack_id"):
        _required_text(request_payload.get("name"), "name")
    _required_text(request_payload.get("niche"), "niche")
    if int(request_payload["requested_asset_count"]) <= 0:
        raise ValueError("requested_asset_count must be positive")
    return jsonable_encoder(request_payload)


@task
def start_asset_pack_generation_run(request_payload: dict[str, Any]) -> dict[str, Any]:
    run_payload = build_asset_pack_generation_runtime().start_run(request_payload)
    return {**request_payload, **run_payload}


@task
def create_asset_pack_step(request_payload: dict[str, Any]) -> dict[str, Any]:
    return build_asset_pack_generation_runtime().create_pack(request_payload)


@task
def create_asset_pack_plan_step(
    request_payload: dict[str, Any],
    pack_payload: dict[str, Any],
) -> dict[str, Any]:
    return build_asset_pack_generation_runtime().create_plan(request_payload, pack_payload)


@task
def approve_asset_pack_step(
    request_payload: dict[str, Any],
    plan_payload: dict[str, Any],
) -> dict[str, Any]:
    return build_asset_pack_generation_runtime().approve_or_wait(request_payload, plan_payload)


@task
def resolve_existing_pack_assets_step(
    request_payload: dict[str, Any],
    plan_payload: dict[str, Any],
) -> dict[str, Any]:
    return build_asset_pack_generation_runtime().resolve_existing_assets(
        request_payload,
        plan_payload,
    )


@task
def generate_missing_pack_assets_step(
    request_payload: dict[str, Any],
    approval_payload: dict[str, Any],
) -> dict[str, Any]:
    return build_asset_pack_generation_runtime().generate_missing_assets(
        request_payload,
        approval_payload,
    )


@task
def register_pack_assets_step(
    request_payload: dict[str, Any],
    generation_payload: dict[str, Any],
) -> dict[str, Any]:
    return build_asset_pack_generation_runtime().register_assets(request_payload, generation_payload)


@task
def mark_asset_pack_ready_step(
    request_payload: dict[str, Any],
    registration_payload: dict[str, Any],
) -> dict[str, Any]:
    return build_asset_pack_generation_runtime().mark_pack_ready(
        request_payload,
        registration_payload,
    )


@task
def emit_asset_pack_generation_notification_step(summary: dict[str, Any]) -> dict[str, Any]:
    return build_asset_pack_generation_runtime().emit_notification(summary)


@task
def mark_asset_pack_generation_failed_step(
    request_payload: dict[str, Any],
    failed_step: str,
    error_message: str,
) -> dict[str, Any]:
    return build_asset_pack_generation_runtime().mark_failed(
        request_payload,
        failed_step=failed_step,
        error_message=error_message,
    )


@flow(name="generate_asset_pack")
def generate_asset_pack(
    *,
    org_id: str,
    name: str | None = None,
    niche: str,
    requested_asset_count: int,
    asset_pack_id: str | None = None,
    purpose: str | None = None,
    target_audience: str | None = None,
    asset_mix: dict[str, int] | None = None,
    target_reel_types: list[str] | None = None,
    style_persona_constraints: dict[str, Any] | None = None,
    auto_approve: bool = True,
    provider: str = "runway",
    model: str = "gen4.5",
    asset_class: str = "component",
    negative_prompt: str | None = None,
    seed: int | None = None,
    duration_seconds: float | None = None,
    fps: int | None = None,
    ratio: str | None = "9:16",
    motion: dict[str, Any] | None = None,
    allow_existing_reuse: bool = True,
    ready_threshold: int | None = None,
    run_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Orchestrate asset-pack planning, review, resolution, and generation intents."""

    _ = orchestrator_service_context()
    request_payload = validate_asset_pack_generation_request(
        {
            "org_id": org_id,
            "asset_pack_id": asset_pack_id,
            "name": name,
            "niche": niche,
            "requested_asset_count": requested_asset_count,
            "purpose": purpose,
            "target_audience": target_audience,
            "asset_mix": asset_mix,
            "target_reel_types": target_reel_types or [],
            "style_persona_constraints": style_persona_constraints or {},
            "auto_approve": auto_approve,
            "provider": provider,
            "model": model,
            "asset_class": asset_class,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "duration_seconds": duration_seconds,
            "fps": fps,
            "ratio": ratio,
            "motion": motion or {},
            "allow_existing_reuse": allow_existing_reuse,
            "ready_threshold": ready_threshold,
            "run_id": run_id,
            "idempotency_key": idempotency_key,
        }
    )
    request_payload = start_asset_pack_generation_run(request_payload)
    failed_step = "create_pack"
    try:
        pack_payload = create_asset_pack_step(request_payload)
        failed_step = "create_plan"
        plan_payload = create_asset_pack_plan_step(request_payload, pack_payload)
        failed_step = "approve_plan"
        approval_payload = approve_asset_pack_step(request_payload, plan_payload)
        if approval_payload.get("status") == "awaiting_approval":
            summary = mark_asset_pack_ready_step(
                request_payload,
                {
                    "asset_pack_id": approval_payload["asset_pack_id"],
                    "resolution_summary": plan_payload.get("planning_resolution_summary", {}),
                    "awaiting_approval": True,
                },
            )
            summary = {
                **summary,
                "awaiting_approval": True,
            }
            emit_asset_pack_generation_notification_step(summary)
            return summary
        failed_step = "resolve_existing_assets"
        resolve_existing_pack_assets_step(request_payload, plan_payload)
        failed_step = "generate_missing_assets"
        generation_payload = generate_missing_pack_assets_step(request_payload, approval_payload)
        failed_step = "register_assets"
        registration_payload = register_pack_assets_step(request_payload, generation_payload)
        failed_step = "mark_pack_ready"
        summary = mark_asset_pack_ready_step(request_payload, registration_payload)
        emit_asset_pack_generation_notification_step(summary)
        return summary
    except Exception as exc:
        mark_asset_pack_generation_failed_step(request_payload, failed_step, str(exc))
        raise


def build_generate_asset_pack_kwargs(args: Namespace) -> dict[str, object]:
    """Map CLI args onto the flow signature."""

    return {
        "org_id": args.org_id,
        "asset_pack_id": args.asset_pack_id,
        "name": args.asset_pack_name,
        "niche": args.niche,
        "requested_asset_count": args.requested_asset_count,
        "auto_approve": args.auto_approve,
        "run_id": args.run_id,
    }


FLOW_DEFINITION = FlowDefinition(
    name="generate_asset_pack",
    description="Plan, approve, resolve, generate, register, and notify for an asset pack.",
    entrypoint=generate_asset_pack,
    build_kwargs=build_generate_asset_pack_kwargs,
)


def _load_run(session: Session, request_payload: Mapping[str, Any]) -> Run:
    run_id = _required_text(request_payload.get("run_id"), "run_id")
    run = session.get(Run, _as_uuid(run_id, field_name="run_id"))
    if run is None:
        raise LookupError(f"Run {run_id} was not found")
    return run


def _load_pack(
    session: Session,
    *,
    request_payload: Mapping[str, Any],
    asset_pack_id: str,
) -> AssetPack:
    pack = (
        session.query(AssetPack)
        .filter(
            AssetPack.org_id == _as_uuid(request_payload["org_id"], field_name="org_id"),
            AssetPack.id == _as_uuid(asset_pack_id, field_name="asset_pack_id"),
        )
        .one_or_none()
    )
    if pack is None:
        raise LookupError(f"Asset pack {asset_pack_id} was not found")
    return pack


def _asset_pack_id(payload: Mapping[str, Any]) -> str:
    nested = payload.get("asset_pack")
    if isinstance(nested, AssetPackOut):
        return str(nested.id)
    if isinstance(nested, Mapping):
        candidate = nested.get("id")
        if candidate is not None:
            return str(candidate)
    candidate = payload.get("asset_pack_id")
    if candidate is not None:
        return str(candidate)
    raise ValueError("payload does not contain an asset_pack_id")


def _as_uuid(value: Any, *, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    normalized = _required_text(value, field_name)
    return uuid.UUID(normalized)


def _required_text(value: Any, field_name: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean values are not valid integers here")
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean values are not valid floats here")
    return float(value)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_or_none(value: Any) -> dict[str, Any] | None:
    mapping = _mapping(value)
    return mapping or None


def _list_of_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


__all__ = [
    "AssetPackGenerationRuntime",
    "FLOW_DEFINITION",
    "SQLAssetPackGenerationRuntime",
    "build_asset_pack_generation_runtime",
    "build_generate_asset_pack_kwargs",
    "generate_asset_pack",
]
