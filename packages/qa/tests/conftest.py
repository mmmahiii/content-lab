"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_llm_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests offline even when the shell has Claude credentials."""

    from content_lab_intelligence.config import CREDENTIAL_ENV_VARS

    for name in CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
