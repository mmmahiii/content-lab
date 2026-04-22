"""Named Prefect flows exposed by the orchestrator package."""

from __future__ import annotations

from .daily_reel_factory import (
    DEFAULT_FACTORY_DISPATCH_MODE,
    daily_reel_factory,
)
from .process_reel import process_reel
from .provider_job_sweeper import provider_job_sweeper
from .registry import (
    DEFAULT_FLOW_NAME,
    FlowDefinition,
    FlowNotFoundError,
    FlowRegistryError,
    get_flow_definition,
    list_flow_definitions,
    list_flow_names,
    run_flow,
)


def example_flow(
    name: str = "world",
    factory_dispatch_mode: str = DEFAULT_FACTORY_DISPATCH_MODE,
) -> dict[str, object]:
    """Backward-compatible alias for the starter scaffold flow."""

    return daily_reel_factory(name=name, factory_dispatch_mode=factory_dispatch_mode)


__all__ = [
    "DEFAULT_FLOW_NAME",
    "DEFAULT_FACTORY_DISPATCH_MODE",
    "FlowDefinition",
    "FlowNotFoundError",
    "FlowRegistryError",
    "daily_reel_factory",
    "example_flow",
    "get_flow_definition",
    "list_flow_definitions",
    "list_flow_names",
    "provider_job_sweeper",
    "process_reel",
    "run_flow",
]
