"""Process-reel orchestration service with persisted run/task/reel state."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, cast

from sqlalchemy.orm import Session

from content_lab_api.db import SessionLocal
from content_lab_api.models.reel import GeneratedReelStatus, Reel
from content_lab_api.models.reel_family import ReelFamily
from content_lab_api.models.run import Run
from content_lab_api.models.task import Task
from content_lab_runs import RunStatus, TaskStatus

PROCESS_REEL_WORKFLOW_KEY = "process_reel"
PROCESS_REEL_TASK_TYPE = "process_reel"
PROCESS_REEL_FLOW_TRIGGER = "orchestrator"
PROCESS_REEL_METADATA_KEY = "process_reel"


class ProcessReelStep(StrEnum):
    """Named phase-1 steps for the first ``process_reel`` skeleton."""

    CREATIVE_PLANNING = "creative_planning"
    ASSET_RESOLUTION = "asset_resolution"
    EDITING = "editing"
    QA = "qa"
    PACKAGING = "packaging"


@dataclass(frozen=True, slots=True)
class ProcessReelStepDefinition:
    """A persisted task boundary and its reel-status transition."""

    step: ProcessReelStep
    reel_status: str | None


PROCESS_REEL_STEP_SEQUENCE: tuple[ProcessReelStepDefinition, ...] = (
    ProcessReelStepDefinition(
        step=ProcessReelStep.CREATIVE_PLANNING,
        reel_status=GeneratedReelStatus.PLANNING.value,
    ),
    ProcessReelStepDefinition(
        step=ProcessReelStep.ASSET_RESOLUTION,
        reel_status=GeneratedReelStatus.GENERATING.value,
    ),
    ProcessReelStepDefinition(
        step=ProcessReelStep.EDITING,
        reel_status=GeneratedReelStatus.EDITING.value,
    ),
    ProcessReelStepDefinition(
        step=ProcessReelStep.QA,
        reel_status=GeneratedReelStatus.QA.value,
    ),
    ProcessReelStepDefinition(
        step=ProcessReelStep.PACKAGING,
        reel_status=None,
    ),
)

PROCESS_REEL_STEP_INDEX: dict[ProcessReelStep, ProcessReelStepDefinition] = {
    definition.step: definition for definition in PROCESS_REEL_STEP_SEQUENCE
}


@dataclass(slots=True)
class ReelRecord:
    """Persisted reel fields needed by the flow skeleton."""

    reel_id: str
    org_id: str
    page_id: str
    reel_family_id: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunRecord:
    """Persisted run fields needed by the flow skeleton."""

    run_id: str
    org_id: str
    status: str
    input_params: dict[str, Any] = field(default_factory=dict)
    output_payload: dict[str, Any] | None = None
    run_metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(slots=True)
class TaskRecord:
    """Persisted task fields needed by the flow skeleton."""

    task_id: str
    task_type: str
    idempotency_key: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class ProcessReelExecution:
    """Serializable execution state that Prefect tasks can pass between steps."""

    reel_id: str
    org_id: str
    page_id: str
    reel_family_id: str
    run_id: str
    dry_run: bool
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def with_output(
        self, step: ProcessReelStep, payload: Mapping[str, Any]
    ) -> ProcessReelExecution:
        next_outputs = dict(self.outputs)
        next_outputs[step.value] = dict(payload)
        return replace(self, outputs=next_outputs)

    def to_payload(self) -> dict[str, Any]:
        return {
            "reel_id": self.reel_id,
            "org_id": self.org_id,
            "page_id": self.page_id,
            "reel_family_id": self.reel_family_id,
            "run_id": self.run_id,
            "dry_run": self.dry_run,
            "outputs": {name: dict(payload) for name, payload in self.outputs.items()},
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ProcessReelExecution:
        outputs_raw = payload.get("outputs", {})
        if not isinstance(outputs_raw, Mapping):
            raise TypeError("outputs must be a mapping")
        return cls(
            reel_id=str(payload["reel_id"]),
            org_id=str(payload["org_id"]),
            page_id=str(payload["page_id"]),
            reel_family_id=str(payload["reel_family_id"]),
            run_id=str(payload["run_id"]),
            dry_run=bool(payload["dry_run"]),
            outputs={
                str(name): dict(cast(Mapping[str, Any], step_payload))
                for name, step_payload in outputs_raw.items()
            },
        )


@dataclass(frozen=True, slots=True)
class ProcessReelQAResult:
    """Business-level outcome of the QA step."""

    passed: bool
    details: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        return {"passed": self.passed, **dict(self.details)}


class ProcessReelExecutor(Protocol):
    """Stub-friendly boundaries for downstream orchestration work."""

    def create_creative_plan(self, execution: ProcessReelExecution) -> dict[str, Any]: ...

    def resolve_assets(self, execution: ProcessReelExecution) -> dict[str, Any]: ...

    def edit_reel(self, execution: ProcessReelExecution) -> dict[str, Any]: ...

    def run_qa(self, execution: ProcessReelExecution) -> ProcessReelQAResult: ...

    def package_reel(self, execution: ProcessReelExecution) -> dict[str, Any]: ...


class ProcessReelRepository(Protocol):
    """Persistence abstraction used by the process-reel service."""

    def get_reel(self, reel_id: str) -> ReelRecord: ...

    def ensure_run(
        self,
        reel: ReelRecord,
        *,
        run_id: str | None,
        input_params: Mapping[str, Any],
        run_metadata: Mapping[str, Any],
    ) -> RunRecord: ...

    def update_run(
        self,
        *,
        run_id: str,
        status: str,
        output_payload: Mapping[str, Any] | None = None,
        metadata_patch: Mapping[str, Any] | None = None,
        set_started_at: bool = False,
        set_finished_at: bool = False,
    ) -> RunRecord: ...

    def ensure_task(
        self,
        *,
        run_id: str,
        org_id: str,
        task_type: str,
        payload: Mapping[str, Any],
        initial_status: str = TaskStatus.PENDING.value,
    ) -> TaskRecord: ...

    def update_task(
        self,
        *,
        run_id: str,
        task_type: str,
        status: str,
        result: Mapping[str, Any] | None = None,
    ) -> TaskRecord: ...

    def update_reel(
        self,
        *,
        reel_id: str,
        status: str,
        metadata_patch: Mapping[str, Any] | None = None,
    ) -> ReelRecord: ...

    def task_statuses(self, run_id: str) -> dict[str, str]: ...


class StubProcessReelExecutor:
    """Default stub executor used until the downstream services become real."""

    def __init__(self, *, qa_passes: bool = True) -> None:
        self._qa_passes = qa_passes

    def create_creative_plan(self, execution: ProcessReelExecution) -> dict[str, Any]:
        return {
            "brief_id": f"brief-{execution.reel_id}",
            "caption_plan": f"stub caption plan for {execution.reel_id}",
            "overlay_plan": ["hook", "cta"],
            "dry_run": execution.dry_run,
        }

    def resolve_assets(self, execution: ProcessReelExecution) -> dict[str, Any]:
        return {
            "decision": "stubbed",
            "asset_refs": [f"asset://{execution.reel_id}/primary"],
            "upstream_brief_id": execution.outputs[ProcessReelStep.CREATIVE_PLANNING.value][
                "brief_id"
            ],
        }

    def edit_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
        return {
            "edit_id": f"edit-{execution.reel_id}",
            "timeline_uri": f"memory://edits/{execution.reel_id}.json",
            "cover_uri": f"memory://covers/{execution.reel_id}.jpg",
        }

    def run_qa(self, execution: ProcessReelExecution) -> ProcessReelQAResult:
        verdict = "pass" if self._qa_passes else "fail"
        return ProcessReelQAResult(
            passed=self._qa_passes,
            details={
                "verdict": verdict,
                "checks": [
                    {
                        "name": "phase1_stub_gate",
                        "verdict": verdict,
                    }
                ],
            },
        )

    def package_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
        return {
            "package_uri": f"memory://packages/{execution.reel_id}.zip",
            "manifest_uri": f"memory://packages/{execution.reel_id}.json",
            "ready_for_publish": True,
        }


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _merge_dicts(
    base: Mapping[str, Any] | None,
    patch: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(base or {})
    if not patch:
        return merged

    for key, value in patch.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            merged[key] = _merge_dicts(cast(Mapping[str, Any], existing), value)
            continue
        merged[key] = value
    return merged


def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID for persisted execution") from exc


class SQLAlchemyProcessReelRepository:
    """Repository backed by the API's Postgres models."""

    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._session_factory = session_factory or SessionLocal

    def get_reel(self, reel_id: str) -> ReelRecord:
        session = self._session_factory()
        try:
            reel_uuid = _parse_uuid(reel_id, field_name="reel_id")
            row = (
                session.query(Reel, ReelFamily.page_id)
                .join(ReelFamily, ReelFamily.id == Reel.reel_family_id)
                .filter(Reel.id == reel_uuid)
                .one_or_none()
            )
            if row is None:
                raise ValueError(f"Unknown reel_id {reel_id!r}")
            reel, page_id = row
            return ReelRecord(
                reel_id=str(reel.id),
                org_id=str(reel.org_id),
                page_id=str(page_id),
                reel_family_id=str(reel.reel_family_id),
                status=reel.status,
                metadata=dict(reel.metadata_ or {}),
            )
        finally:
            session.close()

    def ensure_run(
        self,
        reel: ReelRecord,
        *,
        run_id: str | None,
        input_params: Mapping[str, Any],
        run_metadata: Mapping[str, Any],
    ) -> RunRecord:
        session = self._session_factory()
        try:
            if run_id is not None:
                run = session.get(Run, _parse_uuid(run_id, field_name="run_id"))
                if run is None:
                    raise ValueError(f"Unknown run_id {run_id!r}")
                if str(run.org_id) != reel.org_id:
                    raise ValueError("run org_id does not match reel org_id")
                if run.workflow_key != PROCESS_REEL_WORKFLOW_KEY:
                    raise ValueError("run workflow_key must be 'process_reel'")
                run.run_metadata = _merge_dicts(run.run_metadata, run_metadata)
                if not run.input_params:
                    run.input_params = dict(input_params)
            else:
                run = Run(
                    org_id=_parse_uuid(reel.org_id, field_name="org_id"),
                    workflow_key=PROCESS_REEL_WORKFLOW_KEY,
                    flow_trigger=PROCESS_REEL_FLOW_TRIGGER,
                    status=RunStatus.PENDING.value,
                    input_params=dict(input_params),
                    run_metadata=dict(run_metadata),
                )
                session.add(run)

            session.flush()
            session.commit()
            session.refresh(run)
            return self._to_run_record(run)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_run(
        self,
        *,
        run_id: str,
        status: str,
        output_payload: Mapping[str, Any] | None = None,
        metadata_patch: Mapping[str, Any] | None = None,
        set_started_at: bool = False,
        set_finished_at: bool = False,
    ) -> RunRecord:
        session = self._session_factory()
        try:
            run = session.get(Run, _parse_uuid(run_id, field_name="run_id"))
            if run is None:
                raise ValueError(f"Unknown run_id {run_id!r}")
            run.status = status
            if output_payload is not None:
                run.output_payload = dict(output_payload)
            if metadata_patch:
                run.run_metadata = _merge_dicts(run.run_metadata, metadata_patch)
            if set_started_at and run.started_at is None:
                run.started_at = _utcnow()
            if set_finished_at:
                run.finished_at = _utcnow()
            session.flush()
            session.commit()
            session.refresh(run)
            return self._to_run_record(run)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def ensure_task(
        self,
        *,
        run_id: str,
        org_id: str,
        task_type: str,
        payload: Mapping[str, Any],
        initial_status: str = TaskStatus.PENDING.value,
    ) -> TaskRecord:
        session = self._session_factory()
        try:
            run_uuid = _parse_uuid(run_id, field_name="run_id")
            task = (
                session.query(Task)
                .filter(Task.run_id == run_uuid, Task.task_type == task_type)
                .one_or_none()
            )
            if task is None:
                task = Task(
                    org_id=_parse_uuid(org_id, field_name="org_id"),
                    task_type=task_type,
                    idempotency_key=f"{PROCESS_REEL_WORKFLOW_KEY}:{run_id}:{task_type}",
                    status=initial_status,
                    run_id=run_uuid,
                    payload=dict(payload),
                )
                session.add(task)
            elif not task.payload:
                task.payload = dict(payload)

            session.flush()
            session.commit()
            session.refresh(task)
            return self._to_task_record(task)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_task(
        self,
        *,
        run_id: str,
        task_type: str,
        status: str,
        result: Mapping[str, Any] | None = None,
    ) -> TaskRecord:
        session = self._session_factory()
        try:
            task = (
                session.query(Task)
                .filter(
                    Task.run_id == _parse_uuid(run_id, field_name="run_id"),
                    Task.task_type == task_type,
                )
                .one_or_none()
            )
            if task is None:
                raise ValueError(f"Missing task {task_type!r} for run {run_id!r}")
            task.status = status
            task.result = None if result is None else dict(result)
            session.flush()
            session.commit()
            session.refresh(task)
            return self._to_task_record(task)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_reel(
        self,
        *,
        reel_id: str,
        status: str,
        metadata_patch: Mapping[str, Any] | None = None,
    ) -> ReelRecord:
        session = self._session_factory()
        try:
            reel = session.get(Reel, _parse_uuid(reel_id, field_name="reel_id"))
            if reel is None:
                raise ValueError(f"Unknown reel_id {reel_id!r}")
            reel.status = status
            if metadata_patch:
                reel.metadata_ = _merge_dicts(reel.metadata_, metadata_patch)
            session.flush()
            session.commit()
            session.refresh(reel)
            page_id = (
                session.query(ReelFamily.page_id)
                .filter(ReelFamily.id == reel.reel_family_id)
                .scalar()
            )
            if page_id is None:
                raise ValueError(f"Missing page_id for reel family {reel.reel_family_id!s}")
            return ReelRecord(
                reel_id=str(reel.id),
                org_id=str(reel.org_id),
                page_id=str(page_id),
                reel_family_id=str(reel.reel_family_id),
                status=reel.status,
                metadata=dict(reel.metadata_ or {}),
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def task_statuses(self, run_id: str) -> dict[str, str]:
        session = self._session_factory()
        try:
            rows = (
                session.query(Task.task_type, Task.status)
                .filter(Task.run_id == _parse_uuid(run_id, field_name="run_id"))
                .all()
            )
            return dict(sorted((str(task_type), str(status)) for task_type, status in rows))
        finally:
            session.close()

    @staticmethod
    def _to_run_record(run: Run) -> RunRecord:
        return RunRecord(
            run_id=str(run.id),
            org_id=str(run.org_id),
            status=run.status,
            input_params=dict(run.input_params or {}),
            output_payload=None if run.output_payload is None else dict(run.output_payload),
            run_metadata=dict(run.run_metadata or {}),
            started_at=run.started_at,
            finished_at=run.finished_at,
        )

    @staticmethod
    def _to_task_record(task: Task) -> TaskRecord:
        return TaskRecord(
            task_id=str(task.id),
            task_type=task.task_type,
            idempotency_key=task.idempotency_key,
            status=task.status,
            payload=dict(task.payload or {}),
            result=None if task.result is None else dict(task.result),
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


class InMemoryProcessReelRepository:
    """Test repository that persists run/task/reel changes in memory."""

    def __init__(self) -> None:
        self.reels: dict[str, ReelRecord] = {}
        self.runs: dict[str, RunRecord] = {}
        self.tasks: dict[tuple[str, str], TaskRecord] = {}

    def seed_reel(
        self,
        *,
        reel_id: str,
        org_id: str,
        page_id: str,
        reel_family_id: str,
        status: str = GeneratedReelStatus.DRAFT.value,
        metadata: Mapping[str, Any] | None = None,
    ) -> ReelRecord:
        reel = ReelRecord(
            reel_id=reel_id,
            org_id=org_id,
            page_id=page_id,
            reel_family_id=reel_family_id,
            status=status,
            metadata=dict(metadata or {}),
        )
        self.reels[reel_id] = reel
        return reel

    def get_reel(self, reel_id: str) -> ReelRecord:
        try:
            reel = self.reels[reel_id]
        except KeyError as exc:
            raise ValueError(f"Unknown reel_id {reel_id!r}") from exc
        return replace(reel, metadata=dict(reel.metadata))

    def ensure_run(
        self,
        reel: ReelRecord,
        *,
        run_id: str | None,
        input_params: Mapping[str, Any],
        run_metadata: Mapping[str, Any],
    ) -> RunRecord:
        resolved_run_id = run_id or str(uuid.uuid4())
        run = self.runs.get(resolved_run_id)
        if run is None:
            run = RunRecord(
                run_id=resolved_run_id,
                org_id=reel.org_id,
                status=RunStatus.PENDING.value,
                input_params=dict(input_params),
                run_metadata=dict(run_metadata),
            )
        else:
            run.input_params = dict(run.input_params or input_params)
            run.run_metadata = _merge_dicts(run.run_metadata, run_metadata)
        self.runs[resolved_run_id] = run
        return replace(
            run, input_params=dict(run.input_params), run_metadata=dict(run.run_metadata)
        )

    def update_run(
        self,
        *,
        run_id: str,
        status: str,
        output_payload: Mapping[str, Any] | None = None,
        metadata_patch: Mapping[str, Any] | None = None,
        set_started_at: bool = False,
        set_finished_at: bool = False,
    ) -> RunRecord:
        run = self.runs[run_id]
        run.status = status
        if output_payload is not None:
            run.output_payload = dict(output_payload)
        if metadata_patch:
            run.run_metadata = _merge_dicts(run.run_metadata, metadata_patch)
        if set_started_at and run.started_at is None:
            run.started_at = _utcnow()
        if set_finished_at:
            run.finished_at = _utcnow()
        return replace(
            run,
            input_params=dict(run.input_params),
            output_payload=None if run.output_payload is None else dict(run.output_payload),
            run_metadata=dict(run.run_metadata),
        )

    def ensure_task(
        self,
        *,
        run_id: str,
        org_id: str,
        task_type: str,
        payload: Mapping[str, Any],
        initial_status: str = TaskStatus.PENDING.value,
    ) -> TaskRecord:
        key = (run_id, task_type)
        task = self.tasks.get(key)
        if task is None:
            now = _utcnow()
            task = TaskRecord(
                task_id=str(uuid.uuid4()),
                task_type=task_type,
                idempotency_key=f"{PROCESS_REEL_WORKFLOW_KEY}:{run_id}:{task_type}",
                status=initial_status,
                payload=dict(payload),
                created_at=now,
                updated_at=now,
            )
            self.tasks[key] = task
        return replace(
            task,
            payload=dict(task.payload),
            result=None if task.result is None else dict(task.result),
        )

    def update_task(
        self,
        *,
        run_id: str,
        task_type: str,
        status: str,
        result: Mapping[str, Any] | None = None,
    ) -> TaskRecord:
        task = self.tasks[(run_id, task_type)]
        task.status = status
        task.result = None if result is None else dict(result)
        task.updated_at = _utcnow()
        return replace(
            task,
            payload=dict(task.payload),
            result=None if task.result is None else dict(task.result),
        )

    def update_reel(
        self,
        *,
        reel_id: str,
        status: str,
        metadata_patch: Mapping[str, Any] | None = None,
    ) -> ReelRecord:
        reel = self.reels[reel_id]
        reel.status = status
        if metadata_patch:
            reel.metadata = _merge_dicts(reel.metadata, metadata_patch)
        return replace(reel, metadata=dict(reel.metadata))

    def task_statuses(self, run_id: str) -> dict[str, str]:
        statuses = {
            task_type: task.status
            for (task_run_id, task_type), task in self.tasks.items()
            if task_run_id == run_id
        }
        return dict(sorted(statuses.items()))


class ProcessReelService:
    """Phase-1 ``process_reel`` orchestration service."""

    def __init__(
        self,
        *,
        repository: ProcessReelRepository,
        executor: ProcessReelExecutor | None = None,
        actor: str = "content-lab-orchestrator",
    ) -> None:
        self._repository = repository
        self._executor = executor or StubProcessReelExecutor()
        self._actor = actor

    def start_execution(
        self,
        *,
        reel_id: str,
        dry_run: bool = False,
        run_id: str | None = None,
    ) -> ProcessReelExecution:
        reel = self._repository.get_reel(reel_id)
        input_params = {
            "org_id": reel.org_id,
            "page_id": reel.page_id,
            "reel_id": reel.reel_id,
            "reel_family_id": reel.reel_family_id,
            "dry_run": dry_run,
        }
        run = self._repository.ensure_run(
            reel,
            run_id=run_id,
            input_params=input_params,
            run_metadata={
                "submitted_via": "orchestrator",
                "service": {"actor": self._actor},
                "target": {
                    "org_id": reel.org_id,
                    "page_id": reel.page_id,
                    "reel_id": reel.reel_id,
                    "reel_family_id": reel.reel_family_id,
                },
            },
        )
        self._repository.ensure_task(
            run_id=run.run_id,
            org_id=reel.org_id,
            task_type=PROCESS_REEL_TASK_TYPE,
            payload=input_params,
        )
        for definition in PROCESS_REEL_STEP_SEQUENCE:
            self._repository.ensure_task(
                run_id=run.run_id,
                org_id=reel.org_id,
                task_type=definition.step.value,
                payload=self._step_payload(
                    reel=reel,
                    run_id=run.run_id,
                    dry_run=dry_run,
                    step=definition.step,
                ),
            )

        self._repository.update_run(
            run_id=run.run_id,
            status=RunStatus.RUNNING.value,
            metadata_patch={"service": {"actor": self._actor}},
            set_started_at=True,
        )
        self._repository.update_task(
            run_id=run.run_id,
            task_type=PROCESS_REEL_TASK_TYPE,
            status=TaskStatus.RUNNING.value,
            result={"phase": "running"},
        )
        return ProcessReelExecution(
            reel_id=reel.reel_id,
            org_id=reel.org_id,
            page_id=reel.page_id,
            reel_family_id=reel.reel_family_id,
            run_id=run.run_id,
            dry_run=dry_run,
        )

    def run_creative_planning(self, execution: ProcessReelExecution) -> ProcessReelExecution:
        return self._run_step(
            execution,
            step=ProcessReelStep.CREATIVE_PLANNING,
            action=self._executor.create_creative_plan,
        )

    def run_asset_resolution(self, execution: ProcessReelExecution) -> ProcessReelExecution:
        return self._run_step(
            execution,
            step=ProcessReelStep.ASSET_RESOLUTION,
            action=self._executor.resolve_assets,
        )

    def run_editing(self, execution: ProcessReelExecution) -> ProcessReelExecution:
        return self._run_step(
            execution,
            step=ProcessReelStep.EDITING,
            action=self._executor.edit_reel,
        )

    def run_qa(self, execution: ProcessReelExecution) -> ProcessReelExecution:
        definition = PROCESS_REEL_STEP_INDEX[ProcessReelStep.QA]
        self._transition_reel_if_needed(execution=execution, definition=definition)
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=definition.step.value,
            status=TaskStatus.RUNNING.value,
        )
        try:
            qa_result = self._executor.run_qa(execution)
        except Exception as exc:
            self._repository.update_task(
                run_id=execution.run_id,
                task_type=definition.step.value,
                status=TaskStatus.FAILED.value,
                result={"error": str(exc)},
            )
            raise

        result_payload = qa_result.as_payload()
        qa_task_status = TaskStatus.SUCCEEDED.value if qa_result.passed else TaskStatus.FAILED.value
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=definition.step.value,
            status=qa_task_status,
            result=result_payload,
        )
        return execution.with_output(ProcessReelStep.QA, result_payload)

    def run_packaging(self, execution: ProcessReelExecution) -> ProcessReelExecution:
        return self._run_step(
            execution,
            step=ProcessReelStep.PACKAGING,
            action=self._executor.package_reel,
        )

    def mark_ready(self, execution: ProcessReelExecution) -> dict[str, Any]:
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=PROCESS_REEL_TASK_TYPE,
            status=TaskStatus.SUCCEEDED.value,
        )
        summary = self._build_summary(
            execution,
            reel_status=GeneratedReelStatus.READY.value,
            run_status=RunStatus.SUCCEEDED.value,
        )
        self._repository.update_reel(
            reel_id=execution.reel_id,
            status=GeneratedReelStatus.READY.value,
            metadata_patch={PROCESS_REEL_METADATA_KEY: {"last_summary": summary}},
        )
        self._repository.update_run(
            run_id=execution.run_id,
            status=RunStatus.SUCCEEDED.value,
            output_payload=summary,
            set_finished_at=True,
        )
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=PROCESS_REEL_TASK_TYPE,
            status=TaskStatus.SUCCEEDED.value,
            result=summary,
        )
        return summary

    def mark_qa_failed(self, execution: ProcessReelExecution) -> dict[str, Any]:
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=ProcessReelStep.PACKAGING.value,
            status=TaskStatus.SKIPPED.value,
            result={"reason": GeneratedReelStatus.QA_FAILED.value},
        )
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=PROCESS_REEL_TASK_TYPE,
            status=TaskStatus.FAILED.value,
        )
        summary = self._build_summary(
            execution,
            reel_status=GeneratedReelStatus.QA_FAILED.value,
            run_status=RunStatus.FAILED.value,
        )
        self._repository.update_reel(
            reel_id=execution.reel_id,
            status=GeneratedReelStatus.QA_FAILED.value,
            metadata_patch={PROCESS_REEL_METADATA_KEY: {"last_summary": summary}},
        )
        self._repository.update_run(
            run_id=execution.run_id,
            status=RunStatus.FAILED.value,
            output_payload=summary,
            set_finished_at=True,
        )
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=PROCESS_REEL_TASK_TYPE,
            status=TaskStatus.FAILED.value,
            result=summary,
        )
        return summary

    def mark_failed(
        self,
        execution: ProcessReelExecution,
        *,
        failed_step: str,
        error_message: str,
    ) -> dict[str, Any]:
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=failed_step,
            status=TaskStatus.FAILED.value,
            result={"error": error_message},
        )
        self._skip_downstream_steps(execution.run_id, failed_step=failed_step)
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=PROCESS_REEL_TASK_TYPE,
            status=TaskStatus.FAILED.value,
        )
        current_reel = self._repository.get_reel(execution.reel_id)
        summary = self._build_summary(
            execution,
            reel_status=current_reel.status,
            run_status=RunStatus.FAILED.value,
            error_message=error_message,
        )
        self._repository.update_reel(
            reel_id=execution.reel_id,
            status=current_reel.status,
            metadata_patch={PROCESS_REEL_METADATA_KEY: {"last_summary": summary}},
        )
        self._repository.update_run(
            run_id=execution.run_id,
            status=RunStatus.FAILED.value,
            output_payload=summary,
            set_finished_at=True,
        )
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=PROCESS_REEL_TASK_TYPE,
            status=TaskStatus.FAILED.value,
            result=summary,
        )
        return summary

    def _run_step(
        self,
        execution: ProcessReelExecution,
        *,
        step: ProcessReelStep,
        action: Callable[[ProcessReelExecution], dict[str, Any]],
    ) -> ProcessReelExecution:
        definition = PROCESS_REEL_STEP_INDEX[step]
        self._transition_reel_if_needed(execution=execution, definition=definition)
        self._repository.update_task(
            run_id=execution.run_id,
            task_type=definition.step.value,
            status=TaskStatus.RUNNING.value,
        )
        try:
            result_payload = action(execution)
        except Exception as exc:
            self._repository.update_task(
                run_id=execution.run_id,
                task_type=definition.step.value,
                status=TaskStatus.FAILED.value,
                result={"error": str(exc)},
            )
            raise

        self._repository.update_task(
            run_id=execution.run_id,
            task_type=definition.step.value,
            status=TaskStatus.SUCCEEDED.value,
            result=result_payload,
        )
        return execution.with_output(step, result_payload)

    def _transition_reel_if_needed(
        self,
        *,
        execution: ProcessReelExecution,
        definition: ProcessReelStepDefinition,
    ) -> None:
        if definition.reel_status is None:
            return
        self._repository.update_reel(
            reel_id=execution.reel_id,
            status=definition.reel_status,
            metadata_patch={
                PROCESS_REEL_METADATA_KEY: {
                    "last_run_id": execution.run_id,
                    "current_step": definition.step.value,
                }
            },
        )

    def _skip_downstream_steps(self, run_id: str, *, failed_step: str) -> None:
        found_failed_step = False
        statuses = self._repository.task_statuses(run_id)
        for definition in PROCESS_REEL_STEP_SEQUENCE:
            task_type = definition.step.value
            if task_type == failed_step:
                found_failed_step = True
                continue
            if not found_failed_step:
                continue
            if statuses.get(task_type) != TaskStatus.PENDING.value:
                continue
            self._repository.update_task(
                run_id=run_id,
                task_type=task_type,
                status=TaskStatus.SKIPPED.value,
                result={"reason": "upstream_failed", "failed_step": failed_step},
            )

    def _build_summary(
        self,
        execution: ProcessReelExecution,
        *,
        reel_status: str,
        run_status: str,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        summary = {
            "run_id": execution.run_id,
            "reel_id": execution.reel_id,
            "org_id": execution.org_id,
            "page_id": execution.page_id,
            "reel_family_id": execution.reel_family_id,
            "dry_run": execution.dry_run,
            "reel_status": reel_status,
            "run_status": run_status,
            "step_outputs": {name: dict(payload) for name, payload in execution.outputs.items()},
            "task_statuses": self._repository.task_statuses(execution.run_id),
        }
        if error_message is not None:
            summary["error"] = error_message
        return summary

    @staticmethod
    def _step_payload(
        *,
        reel: ReelRecord,
        run_id: str,
        dry_run: bool,
        step: ProcessReelStep,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "org_id": reel.org_id,
            "page_id": reel.page_id,
            "reel_id": reel.reel_id,
            "reel_family_id": reel.reel_family_id,
            "dry_run": dry_run,
            "step": step.value,
        }


def build_process_reel_service(
    *,
    executor: ProcessReelExecutor | None = None,
    repository: ProcessReelRepository | None = None,
    actor: str = "content-lab-orchestrator",
) -> ProcessReelService:
    """Build the default process-reel service for orchestrator execution."""

    return ProcessReelService(
        repository=repository or SQLAlchemyProcessReelRepository(),
        executor=executor,
        actor=actor,
    )
