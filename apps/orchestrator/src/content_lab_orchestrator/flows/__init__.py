"""Named Prefect flows exposed by the orchestrator package."""

from __future__ import annotations

from .daily_reel_factory import daily_reel_factory
from .process_reel import process_reel
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


def example_flow(name: str = "world") -> dict[str, object]:
    """Backward-compatible alias for the starter scaffold flow."""

    return daily_reel_factory(name=name)


__all__ = [
    "DEFAULT_FLOW_NAME",
    "FlowDefinition",
    "FlowNotFoundError",
    "FlowRegistryError",
    "daily_reel_factory",
    "example_flow",
    "get_flow_definition",
    "list_flow_definitions",
    "list_flow_names",
    "process_reel",
    "run_flow",
]
