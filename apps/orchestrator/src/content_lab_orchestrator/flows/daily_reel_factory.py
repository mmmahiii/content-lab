"""Primary phase-1 orchestration flow for daily reel planning."""

# mypy: disable-error-code="no-any-return,untyped-decorator"

from __future__ import annotations

from argparse import Namespace

from prefect import flow, task

from content_lab_orchestrator.correlation import orchestrator_service_context
from content_lab_runs import build_task_idempotency_key

from .registry import FlowDefinition


def build_daily_reel_factory_task_keys(name: str) -> tuple[str, str, str]:
    """Derive stable task keys for the phase-1 daily factory flow."""

    normalized_name = name.strip()
    return (
        build_task_idempotency_key(
            "daily_reel_factory.choose_target_owned_pages",
            payload={"name": normalized_name},
        ),
        build_task_idempotency_key(
            "daily_reel_factory.load_applicable_policy",
            payload={"name": normalized_name},
        ),
        build_task_idempotency_key(
            "daily_reel_factory.plan_variant_strategy",
            payload={"name": normalized_name},
        ),
    )


@task
def choose_target_owned_pages(seed_name: str) -> list[str]:
    """Select the pages the daily factory should target."""

    return [seed_name]


@task
def load_applicable_policy(target_pages: list[str]) -> dict[str, str]:
    """Load the deterministic policy set used for planning."""

    return {page_name: "phase-1-default" for page_name in target_pages}


@task
def plan_variant_strategy(policy_by_page: dict[str, str]) -> str:
    """Build a stable placeholder summary for the selected targets."""

    target_page = next(iter(sorted(policy_by_page)))
    return f"hello {target_page}"


@flow(name="daily_reel_factory")
def daily_reel_factory(name: str = "world") -> str:
    """Phase-1 daily factory entrypoint for local execution."""

    _ = orchestrator_service_context()
    _ = build_daily_reel_factory_task_keys(name)
    target_pages = choose_target_owned_pages(name)
    policy_by_page = load_applicable_policy(target_pages)
    return plan_variant_strategy(policy_by_page)


def build_daily_reel_factory_kwargs(args: Namespace) -> dict[str, object]:
    """Map CLI arguments onto the flow signature."""

    return {"name": args.name}


FLOW_DEFINITION = FlowDefinition(
    name="daily_reel_factory",
    description="Select owned pages, apply policy, and plan the daily reel batch.",
    entrypoint=daily_reel_factory,
    build_kwargs=build_daily_reel_factory_kwargs,
)
