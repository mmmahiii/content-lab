from __future__ import annotations

import importlib

import pytest

from content_lab_api.services import (
    InMemoryProcessReelRepository,
    ProcessReelService,
    StubProcessReelExecutor,
)
from content_lab_orchestrator.cli import main

process_reel_flow_module = importlib.import_module("content_lab_orchestrator.flows.process_reel")


def test_cli_lists_registered_flows(capsys: pytest.CaptureFixture[str]) -> None:
    main(["list"])

    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["daily_reel_factory", "process_reel"]


def test_cli_runs_default_flow(capsys: pytest.CaptureFixture[str]) -> None:
    main(["run", "--name", "ryan"])

    captured = capsys.readouterr()
    assert captured.out.strip().endswith("hello ryan")


def test_cli_runs_selected_named_flow(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = InMemoryProcessReelRepository()
    repository.seed_reel(
        reel_id="reel-42",
        org_id="org-1",
        page_id="page-7",
        reel_family_id="family-9",
    )
    service = ProcessReelService(
        repository=repository,
        executor=StubProcessReelExecutor(),
    )
    monkeypatch.setattr(process_reel_flow_module, "build_process_reel_runtime", lambda: service)

    main(["run", "--flow", "process_reel", "--reel-id", "reel-42", "--dry-run"])

    captured = capsys.readouterr()
    assert "'reel_status': 'ready'" in captured.out
    assert "'run_status': 'succeeded'" in captured.out


def test_cli_rejects_unknown_flow() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--flow", "missing-flow"])

    assert exc_info.value.code == 2
