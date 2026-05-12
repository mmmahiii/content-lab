"""Run visibility and workflow trigger routes."""
# mypy: disable-error-code="untyped-decorator"

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, insert, or_
from sqlalchemy.orm import Session, selectinload

from content_lab_api.deps import get_db
from content_lab_api.models.audit_log import AuditLog
from content_lab_api.models.org import Org
from content_lab_api.models.outbox import OutboxEvent
from content_lab_api.models.page import Page
from content_lab_api.models.reel import GeneratedReelStatus, Reel, ReelOrigin
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
    outbox_for_run,
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


class PackageGenerationCreate(BaseModel):
    """No-input package generation choice from an approved/selected idea plan."""

    model_config = ConfigDict(extra="forbid")

    generation_mode: Literal["runway", "smoke_test"]


class HookCoverUpdate(BaseModel):
    """Operator edits for an asset-composition hook image."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    editor_state: dict[str, Any] = Field(default_factory=dict)


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


def _now() -> datetime:
    return datetime.now(UTC)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _orchestrator_log_paths(*, run_id: uuid.UUID) -> tuple[Path, Path]:
    log_dir = _repo_root() / ".dev-stack" / "orchestrator-runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{run_id}.out.log", log_dir / f"{run_id}.err.log"


def _launch_process_reel_flow(
    *,
    reel_id: uuid.UUID,
    run_id: uuid.UUID,
    generation_mode: Literal["runway", "smoke_test"],
) -> dict[str, Any]:
    """Launch the real orchestrator process-reel flow in the background."""

    poetry = shutil.which("poetry")
    if poetry is None:
        raise RuntimeError("Poetry is required to launch the process_reel orchestrator flow")

    repo_root = _repo_root()
    orchestrator_dir = repo_root / "apps" / "orchestrator"
    if not orchestrator_dir.exists():
        raise RuntimeError(f"Orchestrator app was not found at {orchestrator_dir}")

    out_log, err_log = _orchestrator_log_paths(run_id=run_id)
    env = os.environ.copy()
    env["POETRY_IGNORE_ACTIVE_VIRTUALENVS"] = "1"
    env.pop("VIRTUAL_ENV", None)
    if generation_mode == "smoke_test":
        env["RUNWAY_API_MODE"] = "mock"

    command = [
        poetry,
        "run",
        "python",
        "-m",
        "content_lab_orchestrator.cli",
        "run",
        "--flow",
        "process_reel",
        "--reel-id",
        str(reel_id),
        "--run-id",
        str(run_id),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with out_log.open("ab") as stdout, err_log.open("ab") as stderr:
        process = subprocess.Popen(
            command,
            cwd=orchestrator_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )

    return {
        "pid": process.pid,
        "command": " ".join(command),
        "stdout_log": str(out_log),
        "stderr_log": str(err_log),
        "runway_api_mode": "mock" if generation_mode == "smoke_test" else "live",
    }


def _idea_plan_payload(*, page: Page, run_id: uuid.UUID, plan_number: int) -> dict[str, Any]:
    handle = page.handle or page.display_name
    title = f"{page.display_name} plan {plan_number}"
    return {
        "plan": {
            "title": title,
            "hook": f"What would make {handle} worth following this week?",
            "angle": "Turn one practical page insight into a clear short-form reel.",
            "beats": [
                {
                    "label": "Hook",
                    "text": "Open with the exact problem the audience already feels.",
                    "seconds": 3,
                },
                {
                    "label": "Proof",
                    "text": "Show the useful shift, example, or operating principle.",
                    "seconds": 6,
                },
                {
                    "label": "Action",
                    "text": "Close with one concrete next step the viewer can try.",
                    "seconds": 3,
                },
            ],
            "caption_angles": [
                "Save this before your next content planning block.",
                "A simple way to turn page strategy into a reel.",
                "Use this as the spine for the next post.",
            ],
            "package_intent": {
                "expected_outputs": [
                    "final_video",
                    "cover",
                    "caption_variants",
                    "posting_plan",
                    "timeline",
                    "creative_trace",
                    "provenance",
                    "package_manifest",
                ],
            },
        },
        "plans": [
            {
                "id": str(run_id),
                "label": f"Plan {plan_number}",
                "title": title,
                "status": "ready_for_generation",
            }
        ],
    }


def _plan_duration_seconds(plan: Mapping[str, Any], *, default: int = 12) -> int:
    beats = plan.get("beats")
    if not isinstance(beats, list):
        return default
    total = 0
    for beat in beats:
        if not isinstance(beat, Mapping):
            continue
        try:
            seconds = int(beat.get("seconds") or 0)
        except (TypeError, ValueError):
            seconds = 0
        if seconds > 0:
            total += seconds
    return total if total >= 5 else default


def _workflow_stage(run: Run) -> str | None:
    metadata = dict(run.run_metadata or {})
    client = metadata.get("client")
    if isinstance(client, dict):
        client_stage = client.get("workflow_stage")
        if isinstance(client_stage, str):
            return client_stage
    input_params = dict(run.input_params or {})
    stage = input_params.get("workflow_stage")
    return stage if isinstance(stage, str) else None


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
def get_run(
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    expand_debug: bool = Query(False),
    db: Session = Depends(get_db),
) -> RunDetailOut:
    run = _get_run_or_404(db, org_id=org_id, run_id=run_id)
    outbox_rows = (
        db.query(OutboxEvent)
        .filter(
            OutboxEvent.org_id == org_id,
            OutboxEvent.aggregate_type == "run",
            OutboxEvent.aggregate_id == str(run_id),
        )
        .order_by(OutboxEvent.created_at.asc())
        .all()
    )
    return run_to_detail(
        run,
        outbox=outbox_for_run(outbox_rows),
        expand_debug=expand_debug,
    )


@router.patch("/orgs/{org_id}/runs/{run_id}/hook-cover", response_model=RunOut)
def update_run_hook_cover(
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    body: HookCoverUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> RunOut:
    run = _get_run_or_404(db, org_id=org_id, run_id=run_id)
    if _workflow_stage(run) != "asset_composition_render":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run is not an asset composition render",
        )

    payload = dict(run.output_payload or {})
    existing_cover = dict(payload.get("hook_cover") or {})
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="title must not be blank",
            )
        existing_cover["title"] = title
    existing_cover["editor_state"] = dict(body.editor_state or {})
    payload["hook_cover"] = existing_cover

    package_payload = dict(payload.get("package") or {})
    if package_payload:
        package_cover = dict(package_payload.get("hook_cover") or {})
        package_cover.update(existing_cover)
        package_payload["hook_cover"] = package_cover
        payload["package"] = package_payload

    run.output_payload = payload
    metadata = dict(run.run_metadata or {})
    metadata["hook_cover_editor"] = {
        "updated_at": _now().isoformat(),
        "actor": request.headers.get("x-actor-id") or ANONYMOUS_ACTOR,
        "title": existing_cover.get("title"),
    }
    run.run_metadata = metadata

    task = (
        db.query(Task)
        .filter(Task.org_id == org_id, Task.run_id == run.id)
        .order_by(Task.updated_at.desc(), Task.id.desc())
        .first()
    )
    if task is not None:
        task.result = payload

    _record_audit(
        db,
        request,
        org_id=org_id,
        action="run.hook_cover.updated",
        resource_type="run",
        resource_id=str(run.id),
        payload={"title": existing_cover.get("title")},
    )
    db.commit()
    db.refresh(run)
    return run_to_out(run)


@router.get("/orgs/{org_id}/pages/{page_id}/runs", response_model=list[RunOut])
def list_page_runs(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[RunOut]:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)

    page_id_value = str(page_id)
    # Use jsonb_extract_path_text instead of chained -> operators: chained
    # ``jsonb->'a'->'b'`` throws on scalar JSON (e.g. legacy or corrupted rows) and
    # aborts the whole query with 500. jsonb_extract_path_text returns NULL instead.
    page_match = or_(
        func.jsonb_extract_path_text(Run.input_params, "page_id") == page_id_value,
        func.jsonb_extract_path_text(Run.run_metadata, "target", "page_id") == page_id_value,
    )
    runs = (
        db.query(Run)
        .filter(
            Run.org_id == org_id,
            page_match,
        )
        .order_by(Run.updated_at.desc(), Run.id.desc())
        .all()
    )
    return [run_to_out(run) for run in runs]


@router.post(
    "/orgs/{org_id}/pages/{page_id}/idea-plans",
    response_model=RunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_page_idea_plan(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> RunOut:
    _get_org_or_404(db, org_id)
    page = _get_page_or_404(db, org_id, page_id)
    plan_number = (
        db.query(func.count(Run.id))
        .filter(
            Run.org_id == org_id,
            func.jsonb_extract_path_text(Run.input_params, "page_id") == str(page_id),
            func.jsonb_extract_path_text(Run.input_params, "workflow_stage") == "idea_plan",
        )
        .scalar()
        or 0
    ) + 1
    run = Run(
        org_id=org_id,
        workflow_key=WorkflowKey.DAILY_REEL_FACTORY.value,
        flow_trigger=FlowTrigger.MANUAL.value,
        status=RunStatus.SUCCEEDED.value,
        input_params={
            "org_id": str(org_id),
            "page_id": str(page_id),
            "workflow_stage": "idea_plan",
            "generation_scope": "ideas_only",
        },
        run_metadata=_build_run_metadata(
            request,
            flow_trigger=FlowTrigger.MANUAL,
            client_metadata={
                "workflow_stage": "idea_plan",
                "ui_label": "Create plan",
            },
            target_metadata={"org_id": str(org_id), "page_id": str(page_id)},
        ),
        started_at=_now(),
        finished_at=_now(),
    )
    db.add(run)
    db.flush()
    run.output_payload = _idea_plan_payload(page=page, run_id=run.id, plan_number=plan_number)
    task = Task(
        org_id=org_id,
        task_type="idea_planning",
        idempotency_key=f"idea-plan:{run.id}",
        status=TaskStatus.SUCCEEDED.value,
        run_id=run.id,
        payload={"page_id": str(page_id)},
        result=run.output_payload,
    )
    db.add(task)
    _record_audit(
        db,
        request,
        org_id=org_id,
        action="idea_plan.created",
        resource_type="run",
        resource_id=str(run.id),
        payload={"page_id": str(page_id), "status": run.status},
    )
    db.commit()
    db.refresh(run)
    return run_to_out(run)


@router.post("/orgs/{org_id}/pages/{page_id}/idea-plans/{run_id}/discard", response_model=RunOut)
def discard_page_idea_plan(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    run_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> RunOut:
    _get_org_or_404(db, org_id)
    _get_page_or_404(db, org_id, page_id)
    run = _get_run_or_404(db, org_id=org_id, run_id=run_id)
    if str(dict(run.input_params or {}).get("page_id")) != str(page_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    if _workflow_stage(run) != "idea_plan":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is not an idea plan")
    payload = dict(run.output_payload or {})
    payload["discarded"] = True
    run.output_payload = payload
    run.status = RunStatus.CANCELLED.value
    run.finished_at = _now()
    metadata = dict(run.run_metadata or {})
    metadata["discarded_at"] = _now().isoformat()
    run.run_metadata = metadata
    _record_audit(
        db,
        request,
        org_id=org_id,
        action="idea_plan.discarded",
        resource_type="run",
        resource_id=str(run.id),
        payload={"page_id": str(page_id)},
    )
    db.commit()
    db.refresh(run)
    return run_to_out(run)


@router.post(
    "/orgs/{org_id}/pages/{page_id}/idea-plans/{run_id}/generate-package",
    response_model=RunOut,
    status_code=status.HTTP_201_CREATED,
)
def generate_package_from_page_idea_plan(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    run_id: uuid.UUID,
    body: PackageGenerationCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> RunOut:
    _get_org_or_404(db, org_id)
    page = _get_page_or_404(db, org_id, page_id)
    plan_run = _get_run_or_404(db, org_id=org_id, run_id=run_id)
    if str(dict(plan_run.input_params or {}).get("page_id")) != str(page_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    if _workflow_stage(plan_run) != "idea_plan":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is not an idea plan")
    if plan_run.status == RunStatus.CANCELLED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plan has been discarded")
    plan_payload = dict(plan_run.output_payload or {})
    if plan_payload.get("used_in_package_run_id") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plan has already been used to generate a package",
        )

    plan = dict(plan_payload.get("plan") or {})
    plan_duration_seconds = _plan_duration_seconds(plan)
    package_metadata: dict[str, object] = {
        "mode": "explore",
        "plan_run_id": str(plan_run.id),
        "generation_mode": body.generation_mode,
        "idea_plan": plan,
    }
    family = ReelFamily(
        org_id=org_id,
        page_id=page_id,
        name=str(plan.get("title") or f"{page.display_name} generated reel"),
        metadata_=package_metadata,
    )
    db.add(family)
    db.flush()
    reel = Reel(
        org_id=org_id,
        reel_family_id=family.id,
        origin=ReelOrigin.GENERATED.value,
        status=GeneratedReelStatus.PLANNING.value,
        variant_label="Runway" if body.generation_mode == "runway" else "Smoke test",
        metadata_={
            "plan_run_id": str(plan_run.id),
            "generation_mode": body.generation_mode,
            "duration_seconds": plan_duration_seconds,
            "idea_plan": plan,
        },
    )
    db.add(reel)
    db.flush()
    run = Run(
        org_id=org_id,
        workflow_key=WorkflowKey.PROCESS_REEL.value,
        flow_trigger=FlowTrigger.MANUAL.value,
        status=RunStatus.QUEUED.value,
        input_params={
            "org_id": str(org_id),
            "page_id": str(page_id),
            "workflow_stage": "package_generation",
            "plan_run_id": str(plan_run.id),
            "generation_mode": body.generation_mode,
            "runway_api_mode": "live" if body.generation_mode == "runway" else "mock",
            "reel_id": str(reel.id),
            "reel_family_id": str(family.id),
            "dry_run": False,
        },
        run_metadata=_build_run_metadata(
            request,
            flow_trigger=FlowTrigger.MANUAL,
            client_metadata={
                "workflow_stage": "package_generation",
                "ui_label": (
                    "Create video with Runway"
                    if body.generation_mode == "runway"
                    else "Create video without paid AI"
                ),
                "generation_mode": body.generation_mode,
                "runway_api_mode": "live" if body.generation_mode == "runway" else "mock",
                "plan_run_id": str(plan_run.id),
            },
            target_metadata={
                "org_id": str(org_id),
                "page_id": str(page_id),
                "reel_id": str(reel.id),
                "reel_family_id": str(family.id),
            },
        ),
    )
    db.add(run)
    db.flush()
    plan_payload["used_in_package_run_id"] = str(run.id)
    plan_payload["used_generation_mode"] = body.generation_mode
    plan_payload["used_at"] = _now().isoformat()
    plan_run.output_payload = plan_payload
    db.add(
        Task(
            org_id=org_id,
            task_type="process_reel",
            idempotency_key=f"process-reel:{run.id}",
            status=TaskStatus.QUEUED.value,
            run_id=run.id,
            payload={
                "page_id": str(page_id),
                "plan_run_id": str(plan_run.id),
                "reel_id": str(reel.id),
                "generation_mode": body.generation_mode,
            },
        )
    )
    _record_audit(
        db,
        request,
        org_id=org_id,
        action="package.generated",
        resource_type="run",
        resource_id=str(run.id),
        payload={
            "page_id": str(page_id),
            "plan_run_id": str(plan_run.id),
            "reel_id": str(reel.id),
            "generation_mode": body.generation_mode,
        },
    )
    db.commit()
    try:
        launch = _launch_process_reel_flow(
            reel_id=reel.id,
            run_id=run.id,
            generation_mode=body.generation_mode,
        )
    except Exception as exc:
        db.rollback()
        fresh_run = db.get(Run, run.id)
        if fresh_run is not None:
            fresh_run.status = RunStatus.FAILED.value
            fresh_run.output_payload = {
                "error": str(exc),
                "phase": "orchestrator_launch",
            }
            fresh_run.finished_at = _now()
            fresh_metadata = dict(fresh_run.run_metadata or {})
            fresh_metadata["orchestrator_launch"] = {"error": str(exc)}
            fresh_run.run_metadata = fresh_metadata
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not launch process_reel: {exc}",
        ) from exc

    fresh_run = db.get(Run, run.id)
    if fresh_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    metadata = dict(fresh_run.run_metadata or {})
    metadata["orchestrator_launch"] = launch
    fresh_run.run_metadata = metadata
    fresh_run.external_ref = f"local-process:{launch['pid']}"
    db.commit()
    db.refresh(fresh_run)
    return run_to_out(fresh_run)


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
