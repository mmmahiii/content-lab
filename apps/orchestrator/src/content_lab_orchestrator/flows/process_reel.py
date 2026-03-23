"""Primary phase-1 orchestration flow for processing an individual reel."""

from __future__ import annotations

from argparse import Namespace

from prefect import flow, task

from content_lab_orchestrator.correlation import orchestrator_service_context

from .registry import FlowDefinition


@task
def validate_reel_context(reel_id: str) -> str:
    """Validate the reel identifier before downstream orchestration."""

    normalized_reel_id = reel_id.strip()
    if not normalized_reel_id:
        raise ValueError("reel_id must not be blank")
    return normalized_reel_id


@task
def build_package_summary(reel_id: str, *, dry_run: bool) -> str:
    """Summarise the canonical phase-1 package processing steps."""

    prefix = "dry-run " if dry_run else ""
    return f"{prefix}processed reel {reel_id}"


@flow(name="process_reel")
def process_reel(reel_id: str = "demo-reel", dry_run: bool = False) -> str:
    """Phase-1 reel processing entrypoint for local execution."""

    _ = orchestrator_service_context()
    validated_reel_id = validate_reel_context(reel_id)
    return build_package_summary(validated_reel_id, dry_run=dry_run)


def build_process_reel_kwargs(args: Namespace) -> dict[str, object]:
    """Map CLI arguments onto the flow signature."""

    return {"reel_id": args.reel_id, "dry_run": args.dry_run}


FLOW_DEFINITION = FlowDefinition(
    name="process_reel",
    description="Validate reel context and run the phase-1 packaging flow.",
    entrypoint=process_reel,
    build_kwargs=build_process_reel_kwargs,
)
