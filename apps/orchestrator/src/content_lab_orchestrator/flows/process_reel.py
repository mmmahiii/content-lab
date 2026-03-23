"""Primary phase-1 orchestration flow for processing an individual reel."""

# mypy: disable-error-code="no-any-return,untyped-decorator"

from __future__ import annotations

from argparse import Namespace
from typing import Any, Protocol, cast

from prefect.flows import flow
from prefect.tasks import task

from content_lab_api.services import build_process_reel_service
from content_lab_orchestrator.correlation import orchestrator_service_context

from .registry import FlowDefinition


class ProcessReelExecutionLike(Protocol):
    """Minimal execution payload contract used inside the orchestrator app."""

    def to_payload(self) -> dict[str, Any]: ...


class ProcessReelRuntime(Protocol):
    """Typed runtime boundary for the API-backed process-reel service."""

    def start_execution(
        self,
        *,
        reel_id: str,
        dry_run: bool = False,
        run_id: str | None = None,
    ) -> ProcessReelExecutionLike: ...

    def run_creative_planning(
        self, execution: ProcessReelExecutionLike
    ) -> ProcessReelExecutionLike: ...

    def run_asset_resolution(
        self, execution: ProcessReelExecutionLike
    ) -> ProcessReelExecutionLike: ...

    def run_editing(self, execution: ProcessReelExecutionLike) -> ProcessReelExecutionLike: ...

    def run_qa(self, execution: ProcessReelExecutionLike) -> ProcessReelExecutionLike: ...

    def run_packaging(self, execution: ProcessReelExecutionLike) -> ProcessReelExecutionLike: ...

    def mark_ready(self, execution: ProcessReelExecutionLike) -> dict[str, Any]: ...

    def mark_qa_failed(self, execution: ProcessReelExecutionLike) -> dict[str, Any]: ...

    def mark_failed(
        self,
        execution: ProcessReelExecutionLike,
        *,
        failed_step: str,
        error_message: str,
    ) -> dict[str, Any]: ...


@task
def validate_reel_context(reel_id: str) -> str:
    """Validate the reel identifier before downstream orchestration."""

    normalized_reel_id = reel_id.strip()
    if not normalized_reel_id:
        raise ValueError("reel_id must not be blank")
    return normalized_reel_id


def build_process_reel_runtime() -> ProcessReelRuntime:
    """Construct the default service runtime for ``process_reel``."""

    context = orchestrator_service_context()
    return cast(
        ProcessReelRuntime,
        build_process_reel_service(actor=context.actor or "content-lab-orchestrator"),
    )


def _execution_from_payload(payload: dict[str, Any]) -> ProcessReelExecutionLike:
    from content_lab_api.services import ProcessReelExecution

    return cast(ProcessReelExecutionLike, ProcessReelExecution.from_payload(payload))


def _execution_to_payload(execution: ProcessReelExecutionLike) -> dict[str, Any]:
    return execution.to_payload()


@task
def start_process_reel(
    reel_id: str,
    *,
    dry_run: bool,
    run_id: str | None,
) -> dict[str, Any]:
    """Create or hydrate the persisted run and task rows for execution."""

    execution = build_process_reel_runtime().start_execution(
        reel_id=reel_id,
        dry_run=dry_run,
        run_id=run_id,
    )
    return _execution_to_payload(execution)


@task
def execute_creative_planning(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Run the creative-planning boundary and persist its task state."""

    execution = _execution_from_payload(execution_payload)
    return _execution_to_payload(build_process_reel_runtime().run_creative_planning(execution))


@task
def execute_asset_resolution(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Run the asset-resolution boundary and persist its task state."""

    execution = _execution_from_payload(execution_payload)
    return _execution_to_payload(build_process_reel_runtime().run_asset_resolution(execution))


@task
def execute_editing(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Run the editing boundary and persist its task state."""

    execution = _execution_from_payload(execution_payload)
    return _execution_to_payload(build_process_reel_runtime().run_editing(execution))


@task
def execute_qa(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Run the QA boundary and persist the QA task outcome."""

    execution = _execution_from_payload(execution_payload)
    return _execution_to_payload(build_process_reel_runtime().run_qa(execution))


@task
def execute_packaging(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Run the packaging boundary and persist its task state."""

    execution = _execution_from_payload(execution_payload)
    return _execution_to_payload(build_process_reel_runtime().run_packaging(execution))


@task
def mark_process_reel_ready(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Mark a successful run as ready/succeeded."""

    execution = _execution_from_payload(execution_payload)
    return build_process_reel_runtime().mark_ready(execution)


@task
def mark_process_reel_qa_failed(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Mark a completed run as ``qa_failed`` and skip packaging."""

    execution = _execution_from_payload(execution_payload)
    return build_process_reel_runtime().mark_qa_failed(execution)


@task
def mark_process_reel_failed(
    execution_payload: dict[str, Any],
    *,
    failed_step: str,
    error_message: str,
) -> dict[str, Any]:
    """Persist an unexpected terminal failure."""

    execution = _execution_from_payload(execution_payload)
    return build_process_reel_runtime().mark_failed(
        execution,
        failed_step=failed_step,
        error_message=error_message,
    )


def _qa_passed(execution_payload: dict[str, Any]) -> bool:
    outputs = execution_payload.get("outputs", {})
    if not isinstance(outputs, dict):
        return False
    qa_payload = outputs.get("qa", {})
    if not isinstance(qa_payload, dict):
        return False
    return bool(qa_payload.get("passed"))


@flow(name="process_reel")
def process_reel(
    reel_id: str = "demo-reel",
    dry_run: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Persist the first phase-1 ``process_reel`` skeleton."""

    _ = orchestrator_service_context()
    validated_reel_id = validate_reel_context(reel_id)
    execution = start_process_reel(validated_reel_id, dry_run=dry_run, run_id=run_id)
    current_step = "creative_planning"

    try:
        execution = execute_creative_planning(execution)
        current_step = "asset_resolution"
        execution = execute_asset_resolution(execution)
        current_step = "editing"
        execution = execute_editing(execution)
        current_step = "qa"
        execution = execute_qa(execution)
        if not _qa_passed(execution):
            return mark_process_reel_qa_failed(execution)
        current_step = "packaging"
        execution = execute_packaging(execution)
        return mark_process_reel_ready(execution)
    except Exception as exc:
        mark_process_reel_failed(
            execution,
            failed_step=current_step,
            error_message=str(exc),
        )
        raise


def build_process_reel_kwargs(args: Namespace) -> dict[str, object]:
    """Map CLI arguments onto the flow signature."""

    return {"reel_id": args.reel_id, "dry_run": args.dry_run, "run_id": args.run_id}


FLOW_DEFINITION = FlowDefinition(
    name="process_reel",
    description="Persist statuses/tasks and run the phase-1 reel-processing skeleton.",
    entrypoint=process_reel,
    build_kwargs=build_process_reel_kwargs,
)
