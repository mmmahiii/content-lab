from __future__ import annotations

import pytest

from content_lab_orchestrator.cli import main


def test_cli_lists_registered_flows(capsys: pytest.CaptureFixture[str]) -> None:
    main(["list"])

    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["daily_reel_factory", "process_reel"]


def test_cli_runs_default_flow(capsys: pytest.CaptureFixture[str]) -> None:
    main(["run", "--name", "ryan"])

    captured = capsys.readouterr()
    assert captured.out.strip().endswith("hello ryan")


def test_cli_runs_selected_named_flow(capsys: pytest.CaptureFixture[str]) -> None:
    main(["run", "--flow", "process_reel", "--reel-id", "reel-42", "--dry-run"])

    captured = capsys.readouterr()
    assert captured.out.strip().endswith("dry-run processed reel reel-42")


def test_cli_rejects_unknown_flow() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--flow", "missing-flow"])

    assert exc_info.value.code == 2
