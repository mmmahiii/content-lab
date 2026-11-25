"""Orchestrator test session setup.

Prefect's ephemeral API client uses ``asgi_lifespan.LifespanManager`` with a 30s
startup timeout (see ``prefect.client.base.app_lifespan_context``). Under a full
``py_check`` run (many packages + sequential pytest), startup can exceed 30s on
loaded machines, causing flaky ``TimeoutError`` in flow integration tests.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Patch Prefect client lifespan timeouts before any tests import flows."""

    del config  # unused; required by pytest hook signature
    from content_lab_orchestrator.prefect_compat import (
        extend_prefect_ephemeral_lifespan_timeout,
    )

    extend_prefect_ephemeral_lifespan_timeout()


@pytest.fixture(autouse=True)
def _no_llm_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests offline even when the shell has Claude credentials."""

    from content_lab_intelligence.config import CREDENTIAL_ENV_VARS

    for name in CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
