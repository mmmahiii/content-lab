"""Primary phase-1 orchestration flow for daily reel planning."""

from __future__ import annotations

from argparse import Namespace

from prefect import flow, task

from content_lab_orchestrator.correlation import orchestrator_service_context

from .registry import FlowDefinition


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
