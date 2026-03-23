"""Discovery and registration utilities for local Prefect flow execution."""

from __future__ import annotations

import importlib
import pkgutil
from argparse import Namespace
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_FLOW_NAME = "daily_reel_factory"
_FLOW_PACKAGE_NAME = __name__.rsplit(".", 1)[0]
_FLOW_PACKAGE_PATH = Path(__file__).resolve().parent
_EXCLUDED_MODULE_NAMES = frozenset({"registry"})


@dataclass(frozen=True, slots=True)
class FlowDefinition:
    """Named flow metadata exposed to the CLI."""

    name: str
    description: str
    entrypoint: Callable[..., object]
    build_kwargs: Callable[[Namespace], dict[str, object]]


class FlowRegistryError(RuntimeError):
    """Raised when flow registration metadata is invalid."""


class FlowNotFoundError(LookupError):
    """Raised when a named flow is not registered."""


def _iter_flow_module_names() -> tuple[str, ...]:
    module_names = []
    for module_info in pkgutil.iter_modules([str(_FLOW_PACKAGE_PATH)]):
        if module_info.name.startswith("_") or module_info.name in _EXCLUDED_MODULE_NAMES:
            continue
        module_names.append(module_info.name)
    return tuple(sorted(module_names))


@lru_cache(maxsize=1)
def list_flow_definitions() -> tuple[FlowDefinition, ...]:
    """Discover registered flow modules under ``content_lab_orchestrator.flows``."""

    definitions: dict[str, FlowDefinition] = {}
    for module_name in _iter_flow_module_names():
        module = importlib.import_module(f"{_FLOW_PACKAGE_NAME}.{module_name}")
        definition = getattr(module, "FLOW_DEFINITION", None)
        if definition is None:
            continue
        if not isinstance(definition, FlowDefinition):
            raise FlowRegistryError(
                f"Flow module '{module_name}' must export a FlowDefinition named FLOW_DEFINITION"
            )
        if definition.name in definitions:
            raise FlowRegistryError(
                f"Duplicate orchestrator flow registration: '{definition.name}'"
            )
        definitions[definition.name] = definition

    return tuple(sorted(definitions.values(), key=lambda flow_definition: flow_definition.name))


def list_flow_names() -> tuple[str, ...]:
    """Return registered flow names in deterministic order."""

    return tuple(flow_definition.name for flow_definition in list_flow_definitions())


def get_flow_definition(name: str) -> FlowDefinition:
    """Return a flow registration by name."""

    for flow_definition in list_flow_definitions():
        if flow_definition.name == name:
            return flow_definition

    available_flows = ", ".join(list_flow_names()) or "<none>"
    raise FlowNotFoundError(
        f"Unknown orchestrator flow '{name}'. Available flows: {available_flows}"
    )


def run_flow(flow_name: str, **kwargs: object) -> object:
    """Execute a named flow with explicit keyword arguments."""

    return get_flow_definition(flow_name).entrypoint(**kwargs)
