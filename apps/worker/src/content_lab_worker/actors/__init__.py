"""Actor discovery and registration for the worker entrypoint."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pkgutil import iter_modules
from types import ModuleType

from content_lab_worker.actors._shared import ActorLike, get_actor_logger

logger = get_actor_logger("registry")
_PACKAGE_PATHS = tuple(str(path) for path in globals().get("__path__", ()))


@dataclass(frozen=True)
class ActorRegistration:
    module_names: tuple[str, ...]
    modules: tuple[ModuleType, ...]
    actors: tuple[ActorLike, ...]


def discover_actor_module_names() -> tuple[str, ...]:
    module_names = [
        module_info.name
        for module_info in iter_modules(_PACKAGE_PATHS, prefix=f"{__name__}.")
        if not module_info.name.rsplit(".", maxsplit=1)[-1].startswith("_")
    ]
    return tuple(sorted(module_names))


def _collect_registered_actors(modules: tuple[ModuleType, ...]) -> tuple[ActorLike, ...]:
    actors: list[ActorLike] = []
    for module in modules:
        module_actors = getattr(module, "ACTORS", ())
        actors.extend(module_actors)
    return tuple(actors)


def register_actor_modules() -> ActorRegistration:
    module_names = discover_actor_module_names()
    modules = tuple(importlib.import_module(module_name) for module_name in module_names)
    actors = _collect_registered_actors(modules)
    logger.info(
        "registered %s actor modules (%s actors): %s",
        len(modules),
        len(actors),
        ", ".join(module_names),
    )
    return ActorRegistration(module_names=module_names, modules=modules, actors=actors)


__all__ = ["ActorRegistration", "discover_actor_module_names", "register_actor_modules"]
