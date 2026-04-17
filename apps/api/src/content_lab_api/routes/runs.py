"""Run visibility and workflow trigger routes."""
# mypy: disable-error-code="untyped-decorator"

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import insert, or_
from sqlalchemy.orm import Session, selectinload

from content_lab_api.deps import get_db
from content_lab_api.models.audit_log import AuditLog
from content_lab_api.models.org import Org
from content_lab_api.models.outbox import OutboxEvent
from content_lab_api.models.page import Page
from content_lab_api.models.reel import Reel
from content_lab_api.models.reel_family import ReelFamily
from content_lab_api.models.run import Run
from content_lab_api.models.task import Task
from content_lab_api.schemas.runs import (
    FlowTrigger,
    ReelTriggerCreate,
    RunCreate,
    RunDetailOut,
    RunOut,
    WorkflowKey,
    run_to_detail,
    run_to_out,
)
from content_lab_api.services import apply_task_row_spec, create_run_row, create_task_row
from content_lab_runs import (
    DuplicateIdempotencyKeyError,
    RunRowSpec,
    RunStatus,
    TaskRowSpec,
    TaskStatus,
    build_task_idempotency_key,
    task_status_for_run_status,
)
from content_lab_shared.logging import ANONYMOUS_ACTOR

router = APIRouter(tags=["runs"])

_RESERVED_REEL_TRIGGER_KEYS = frozenset({"org_id", "page_id", "reel_id", "reel_family_id"})
_RUN_STATUS_QUEUED = RunStatus.QUEUED.value


@dataclass(slots=True)
class OrchestrationTriggerResult:
    """Outcome returned by the orchestration adapter."""

    external_ref: str | None = None
    status: str = _RUN_STATUS_QUEUED
    backend_name: str = "outbox"
    metadata: dict[str, Any] = field(default_factory=dict)


class OrchestrationBackend(Protocol):
    """Thin adapter the API uses to ask orchestration to start work."""

    def trigger_flow(
        self,
        *,
        db: Session,
        run: Run,
        request: Request,
    ) -> OrchestrationTriggerResult: ...


class OutboxOrchestrationBackend:
    """Persist orchestration intent into the transactional outbox."""

    backend_name = "outbox"
    event_type = "orchestration.flow.requested"

    def trigger_flow(
        self,
        *,
        db: Session,
        run: Run,
        request: Request,
    ) -> OrchestrationTriggerResult:
        event = OutboxEvent(
            org_id=run.org_id,
            aggregate_type="run",
            aggregate_id=str(run.id),
            event_type=self.event_type,
            payload={
                "run_id": str(run.id),
                "org_id": str(run.org_id),
                "workflow_key": run.workflow_key,
                "flow_trigger": run.flow_trigger,
                "status": _RUN_STATUS_QUEUED,
                "idempotency_key": run.idempotency_key,
                "input_params": dict(run.input_params or {}),
                "run_metadata": dict(run.run_metadata or {}),
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        db.add(event)
        db.flush()
        return OrchestrationTriggerResult(
            external_ref=f"outbox:{event.id}",
            status=_RUN_STATUS_QUEUED,
            backend_name=self.backend_name,
            metadata={
                "event_type": self.event_type,
                "outbox_event_id": str(event.id),
            },
        )


def get_orchestration_backend() -> OrchestrationBackend:
    """Dependency hook for the orchestration adapter."""

    return OutboxOrchestrationBackend()


def _get_org_or_404(db: Session, org_id: uuid.UUID) -> Org:
    org = db.get(Org, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    return org


def _get_page_or_404(db: Session, org_id: uuid.UUID, page_id: uuid.UUID) -> Page:
    page = db.query(Page).filter(Page.org_id == org_id, Page.id == page_id).one_or_none()
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return page


def _get_reel_or_404(
    db: Session,
    *,
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    reel_id: uuid.UUID,
) -> Reel:
    reel = (
        db.query(Reel)
        .join(ReelFamily, ReelFamily.id == Reel.reel_family_id)
        .filter(
            Reel.org_id == org_id,
            Reel.id == reel_id,
            ReelFamily.org_id == org_id,
            ReelFamily.page_id == page_id,
        )
        .one_or_none()
    )
    if reel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reel not found")
    return reel


def _get_run_or_404(db: Session, *, org_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    run = (
        db.query(Run)
        .options(selectinload(Run.tasks))
        .filter(Run.org_id == org_id, Run.id == run_id)
        .one_or_none()
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


def _actor_info(request: Request) -> tuple[str | None, str]:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    return actor_id, actor_type


def _request_metadata(request: Request, *, flow_trigger: FlowTrigger) -> dict[str, Any]:
    actor_id, actor_type = _actor_info(request)
    return {
        "submitted_via": "api",
        "flow_trigger": flow_trigger.value,
        "actor": {
            "id": actor_id,
            "type": actor_type,
        },
        "request": {
            "request_id": getattr(request.state, "request_id", None),
            "method": request.method,
            "path": request.url.path,
        },
    }


def _record_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict[str, Any],
) -> None:
    actor_id, actor_type = _actor_info(request)
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action=action,
            resource_type=resource_type,
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=resource_id,
            payload=payload,
        )
    )


def _raise_conflict(exc: DuplicateIdempotencyKeyError) -> None:
    if exc.record_type == "run":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A run with this idempotency_key already exists for the org",
        ) from exc
    if exc.record_type == "task":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A matching trigger task already exists for the org",
        ) from exc
    raise exc


def _build_run_metadata(
    request: Request,
    *,
    flow_trigger: FlowTrigger,
    client_metadata: dict[str, Any],
    target_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = _request_metadata(request, flow_trigger=flow_trigger)
    if client_metadata:
        metadata["client"] = dict(client_metadata)
    if target_metadata:
        metadata["target"] = dict(target_metadata)
    return metadata


def _task_spec_for_run_status(task_spec: TaskRowSpec, *, run_status: str) -> TaskRowSpec:
    task_status = task_status_for_run_status(run_status)
    if task_status is TaskStatus.QUEUED:
        return task_spec.queued()
    if task_status is TaskStatus.RUNNING:
        return task_spec.running()
    if task_status is TaskStatus.RETRYING:
        return task_spec.retrying()
    if task_status is TaskStatus.SUCCEEDED:
        return task_spec.succeeded()
    if task_status is TaskStatus.FAILED:
        return task_spec.failed()
    if task_status is TaskStatus.SKIPPED:
        return task_spec.skipped()
    return task_spec


def _trigger_run(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    workflow_key: WorkflowKey,
    flow_trigger: FlowTrigger,
    input_params: dict[str, Any],
    client_metadata: dict[str, Any],
    idempotency_key: str | None,
    orchestration_backend: OrchestrationBackend,
    task_idempotency_key: str | None = None,
    target_metadata: dict[str, Any] | None = None,
) -> tuple[Run, Task | None]:
    run = create_run_row(
        db,
        spec=RunRowSpec(
            org_id=org_id,
            workflow_key=workflow_key.value,
            flow_trigger=flow_trigger.value,
            idempotency_key=idempotency_key,
            status=RunStatus.PENDING,
            input_params=dict(input_params),
            run_metadata=_build_run_metadata(
                request,
                flow_trigger=flow_trigger,
                client_metadata=client_metadata,
                target_metadata=target_metadata,
            ),
        ),
    )

    task: Task | None = None
    task_spec: TaskRowSpec | None = None
    if task_idempotency_key is not None:
        task_spec = TaskRowSpec(
            org_id=org_id,
            task_type=workflow_key.value,
            idempotency_key=task_idempotency_key,
            status=TaskStatus.PENDING,
            run_id=run.id,
            payload=dict(input_params),
        )
        task = create_task_row(db, spec=task_spec)

    trigger_result = orchestration_backend.trigger_flow(db=db, run=run, request=request)
    run.status = trigger_result.status
    run.external_ref = trigger_result.external_ref
    run_metadata = dict(run.run_metadata or {})
    run_metadata["orchestration"] = {
        "backend": trigger_result.backend_name,
        **dict(trigger_result.metadata),
    }
    run.run_metadata = run_metadata

    if task is not None and task_spec is not None:
        apply_task_row_spec(
            task,
            spec=_task_spec_for_run_status(task_spec, run_status=trigger_result.status),
        )

    return run, task


def _reel_trigger_input_params(
    *,
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    reel: Reel,
    body: ReelTriggerCreate,
) -> dict[str, Any]:
    overlapping_keys = sorted(set(body.input_params).intersection(_RESERVED_REEL_TRIGGER_KEYS))
    if overlapping_keys:
        joined = ", ".join(overlapping_keys)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"input_params must not include reserved key(s): {joined}",
        )
    return {
        **dict(body.input_params),
        "org_id": str(org_id),
        "page_id": str(page_id),
        "reel_id": str(reel.id),
        "reel_family_id": str(reel.reel_family_id),
    }


@router.post("/orgs/{org_id}/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(
    org_id: uuid.UUID,
    body: RunCreate,
    request: Request,
    db: Session = Depends(get_db),
    orchestration_backend: OrchestrationBackend = Depends(get_orchestration_backend),
) -> RunOut:
    _get_org_or_404(db, org_id)
    try:
        run, _ = _trigger_run(
            db,
            request,
            org_id=org_id,
            workflow_key=body.workflow_key,
            flow_trigger=FlowTrigger.MANUAL,
            input_params=body.input_params,
            client_metadata=body.metadata,
            idempotency_key=body.idempotency_key,
            orchestration_backend=orchestration_backend,
        )
        _record_audit(
            db,
            request,
            org_id=org_id,
            action="run.created",
            resource_type="run",
            resource_id=str(run.id),
            payload={
                "workflow_key": run.workflow_key,
                "flow_trigger": run.flow_trigger,
                "status": run.status,
                "external_ref": run.external_ref,
                "idempotency_key": run.idempotency_key,
            },
        )
        db.commit()
    except DuplicateIdempotencyKeyError as exc:
        db.rollback()
        _raise_conflict(exc)
    except Exception:
        db.rollback()
        raise

    db.refresh(run)
    return run_to_out(run)


@router.get("/orgs/{org_id}/runs/{run_id}", response_model=RunDetailOut)
def get_run(org_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db)) -> RunDetailOut:
    run = _get_run_or_404(db, org_id=org_id, run_id=run_id)
    return run_to_detail(run)


@router.get("/orgs/{org_id}/pages/{page_id}/runs", response_model=list[RunOut])
def list_page_runs(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[RunOut]:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)

    page_id_value = str(page_id)
    runs = (
        db.query(Run)
        .filter(
            Run.org_id == org_id,
            or_(
                Run.input_params["page_id"].astext == page_id_value,
                Run.run_metadata["target"]["page_id"].astext == page_id_value,
            ),
        )
        .order_by(Run.updated_at.desc(), Run.id.desc())
        .all()
    )
    return [run_to_out(run) for run in runs]


@router.post(
    "/orgs/{org_id}/pages/{page_id}/reels/{reel_id}/trigger",
    response_model=RunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_reel_workflow(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    reel_id: uuid.UUID,
    body: ReelTriggerCreate,
    request: Request,
    db: Session = Depends(get_db),
    orchestration_backend: OrchestrationBackend = Depends(get_orchestration_backend),
) -> RunOut:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)
    reel = _get_reel_or_404(db, org_id=org_id, page_id=page_id, reel_id=reel_id)

    input_params = _reel_trigger_input_params(org_id=org_id, page_id=page_id, reel=reel, body=body)
    trigger_identity_payload = {
        "org_id": str(org_id),
        "page_id": str(page_id),
        "reel_id": str(reel.id),
    }
    trigger_idempotency_key = body.idempotency_key or build_task_idempotency_key(
        WorkflowKey.PROCESS_REEL.value,
        payload=trigger_identity_payload,
    )
    target_metadata = {
        "org_id": str(org_id),
        "page_id": str(page_id),
        "reel_id": str(reel.id),
        "reel_family_id": str(reel.reel_family_id),
    }

    try:
        run, task = _trigger_run(
            db,
            request,
            org_id=org_id,
            workflow_key=WorkflowKey.PROCESS_REEL,
            flow_trigger=FlowTrigger.REEL_TRIGGER,
            input_params=input_params,
            client_metadata=body.metadata,
            idempotency_key=trigger_idempotency_key,
            orchestration_backend=orchestration_backend,
            task_idempotency_key=trigger_idempotency_key,
            target_metadata=target_metadata,
        )
        _record_audit(
            db,
            request,
            org_id=org_id,
            action="reel.triggered",
            resource_type="reel",
            resource_id=str(reel.id),
            payload={
                "workflow_key": run.workflow_key,
                "run_id": str(run.id),
                "task_id": None if task is None else str(task.id),
                "page_id": str(page_id),
                "reel_family_id": str(reel.reel_family_id),
                "status": run.status,
                "external_ref": run.external_ref,
                "idempotency_key": run.idempotency_key,
            },
        )
        db.commit()
    except DuplicateIdempotencyKeyError as exc:
        db.rollback()
        _raise_conflict(exc)
    except Exception:
        db.rollback()
        raise

    db.refresh(run)
    return run_to_out(run)
