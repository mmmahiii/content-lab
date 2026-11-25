"""Prefect 2.x runtime adjustments shared by the CLI and the test suite.

Prefect's ephemeral API client starts an in-process server through
``asgi_lifespan.LifespanManager`` with a hard-coded 30 s startup timeout
(``prefect.client.base.app_lifespan_context``). A cold start (fresh container, first
SQLite migration, loaded machine) can exceed that, so every flow run failed with a bare
``TimeoutError`` before any work started.
"""

from __future__ import annotations

from typing import Any

PREFECT_EPHEMERAL_LIFESPAN_TIMEOUT_SECONDS = 120.0
_patched = False


def extend_prefect_ephemeral_lifespan_timeout(
    seconds: float = PREFECT_EPHEMERAL_LIFESPAN_TIMEOUT_SECONDS,
) -> None:
    """Raise Prefect's ephemeral API startup/shutdown timeout to at least ``seconds``."""

    global _patched
    if _patched:
        return
    import prefect.client.base as prefect_client_base

    original = prefect_client_base.LifespanManager

    def _lifespan_manager(
        app: Any,
        startup_timeout: float | None = 30,
        shutdown_timeout: float | None = 30,
    ) -> Any:
        return original(
            app,
            startup_timeout=max(float(startup_timeout or 0.0), seconds),
            shutdown_timeout=max(float(shutdown_timeout or 0.0), seconds),
        )

    prefect_client_base.LifespanManager = _lifespan_manager  # type: ignore[method-assign]
    _patched = True


__all__ = [
    "PREFECT_EPHEMERAL_LIFESPAN_TIMEOUT_SECONDS",
    "extend_prefect_ephemeral_lifespan_timeout",
]
