"""Keep creative tests offline even when the developer's shell has Claude credentials."""

from __future__ import annotations

import pytest

from content_lab_intelligence.config import CREDENTIAL_ENV_VARS


@pytest.fixture(autouse=True)
def _no_llm_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
