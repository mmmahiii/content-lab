"""Orchestrator test session setup.

Prefect's ephemeral API client uses ``asgi_lifespan.LifespanManager`` with a 30s
startup timeout (see ``prefect.client.base.app_lifespan_context``). Under a full
``py_check`` run (many packages + sequential pytest), startup can exceed 30s on
loaded machines, causing flaky ``TimeoutError`` in flow integration tests.
"""

from __future__ import annotations

from typing import Any

import pytest

# Minimum startup/shutdown wait for ephemeral Prefect API (seconds).
_PREFECT_EPHEMERAL_LIFESPAN_TIMEOUT = 120.0
_PREFECT_LIFESPAN_PATCHED = False


def pytest_configure(config: pytest.Config) -> None:
    """Patch Prefect client lifespan timeouts before any tests import flows."""
    del config  # unused; required by pytest hook signature
    global _PREFECT_LIFESPAN_PATCHED
    if _PREFECT_LIFESPAN_PATCHED:
        return

    import prefect.client.base as prefect_client_base

    _OriginalLifespanManager = prefect_client_base.LifespanManager

    def _LifespanManager(  # noqa: N802
        app: Any,
        startup_timeout: float | None = 30,
        shutdown_timeout: float | None = 30,
    ) -> Any:
        return _OriginalLifespanManager(
            app,
            startup_timeout=max(
                float(startup_timeout) if startup_timeout is not None else 0.0,
                _PREFECT_EPHEMERAL_LIFESPAN_TIMEOUT,
            ),
            shutdown_timeout=max(
                float(shutdown_timeout) if shutdown_timeout is not None else 0.0,
                _PREFECT_EPHEMERAL_LIFESPAN_TIMEOUT,
            ),
        )

    prefect_client_base.LifespanManager = _LifespanManager  # type: ignore[method-assign]
    _PREFECT_LIFESPAN_PATCHED = True
