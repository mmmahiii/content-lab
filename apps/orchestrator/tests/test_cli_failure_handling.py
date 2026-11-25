"""The CLI is launched detached by the API, so it must record its own crashes."""

from __future__ import annotations

import argparse

import pytest

from content_lab_orchestrator import cli
from content_lab_orchestrator.prefect_compat import extend_prefect_ephemeral_lifespan_timeout


def _args(run_id: str | None) -> argparse.Namespace:
    return cli._build_parser().parse_args(
        [
            "run",
            "--flow",
            "process_reel",
            "--reel-id",
            "r1",
            *(["--run-id", run_id] if run_id else []),
        ]
    )


def test_crash_marks_the_run_failed_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    marked: list[tuple[str, str]] = []

    def _boom(*_: object, **__: object) -> None:
        raise TimeoutError("prefect ephemeral api did not start")

    monkeypatch.setattr(cli, "run_flow", _boom)
    monkeypatch.setattr(
        cli, "_mark_run_failed", lambda run_id, *, error: marked.append((run_id, error))
    )
    with pytest.raises(TimeoutError):
        cli._run_selected_flow(_args("11111111-1111-4111-8111-111111111111"))
    assert marked == [
        (
            "11111111-1111-4111-8111-111111111111",
            "TimeoutError: prefect ephemeral api did not start",
        )
    ]


def test_crash_without_run_id_does_not_touch_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_flow", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(
        cli, "_mark_run_failed", lambda *_a, **_k: pytest.fail("should not be called")
    )
    with pytest.raises(RuntimeError):
        cli._run_selected_flow(_args(None))


def test_lifespan_timeout_patch_is_applied_once() -> None:
    import prefect.client.base as prefect_client_base

    extend_prefect_ephemeral_lifespan_timeout()
    patched = prefect_client_base.LifespanManager
    extend_prefect_ephemeral_lifespan_timeout()
    assert prefect_client_base.LifespanManager is patched
    assert patched.__name__ == "_lifespan_manager"
