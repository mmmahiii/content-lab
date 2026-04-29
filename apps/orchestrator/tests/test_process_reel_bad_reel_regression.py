from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from content_lab_api.services import ProcessReelExecution, ProcessReelQAResult
from content_lab_core.types import QAVerdict
from content_lab_orchestrator.flows.process_reel import PhaseOneProcessReelExecutor
from content_lab_qa.format import FormatQAReport, ProbedMedia
from content_lab_qa.overlay import OverlayTextFidelityReport


def _dummy_passing_overlay(*, script: object, editing: object | None = None) -> OverlayTextFidelityReport:
    return OverlayTextFidelityReport(
        verdict=QAVerdict.PASS,
        message="overlay QA patched in bad-reel regression tests",
        findings=(),
    )

# apps/orchestrator/tests/ -> worktree root -> packages/
_PACKAGES_ROOT = Path(__file__).resolve().parents[3] / "packages"
_BAD_REEL_DIR = _PACKAGES_ROOT / "qa" / "tests" / "fixtures" / "bad_reels" / "cases"
_FIXTURE_VERSION = "bad_reel_fixture_v1"

# Import the *module* (not the @flow `process_reel` re-exported from `flows` package).
_process_reel_module = importlib.import_module("content_lab_orchestrator.flows.process_reel")


def _load_bad_reel_case(case_id: str) -> dict[str, Any]:
    path = _BAD_REEL_DIR / f"{case_id}.json"
    data = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    if data.get("case_id") != case_id or data.get("schema_version") != _FIXTURE_VERSION:
        raise ValueError(f"Unexpected bundle in {path}")
    return data


def _dummy_passing_format_report() -> FormatQAReport:
    video = ProbedMedia(
        path="C:/fixtures/dummy/final_video.mp4",
        exists=True,
        width=1080,
        height=1920,
        duration_seconds=12.0,
        has_audio=True,
    )
    cover = ProbedMedia(
        path="C:/fixtures/dummy/cover.png",
        exists=True,
        width=1080,
        height=1920,
    )
    return FormatQAReport(
        verdict=QAVerdict.PASS,
        message="technical format OK (patched in test)",
        checks=(),
        failure_reasons=(),
        final_video=video,
        cover=cover,
    )


def _execution_for_bundle(*, case_id: str) -> ProcessReelExecution:
    bundle = _load_bad_reel_case(case_id)
    planning = {
        "brief": bundle["brief"],
        "script": bundle["script"],
        "scene_plan": bundle["scene_plan"],
        "compiled_prompt": bundle["compiled_prompt"],
    }
    return ProcessReelExecution(
        reel_id="00000000-0000-4000-8000-000000000001",
        org_id="00000000-0000-4000-8000-000000000002",
        page_id="00000000-0000-4000-8000-000000000003",
        reel_family_id="00000000-0000-4000-8000-000000000004",
        run_id="00000000-0000-4000-8000-000000000005",
        dry_run=False,
        outputs={
            "creative_planning": planning,
            "editing": bundle["editing"],
            "asset_resolution": bundle["asset_resolution"],
        },
    )


def test_process_reel_qa_fails_on_semantic_drift_with_technical_format_patched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With format/repetition treated as technical passes, bad-output drift must still fail QA."""

    monkeypatch.setattr(
        _process_reel_module,
        "evaluate_format_qa",
        lambda **kwargs: _dummy_passing_format_report(),
    )
    monkeypatch.setattr(
        _process_reel_module,
        "evaluate_overlay_text_fidelity_qa",
        lambda *, script, editing=None: _dummy_passing_overlay(script=script, editing=editing),
    )
    ex = _execution_for_bundle(case_id="intent_drift_solar_mismatch")
    executor = object.__new__(PhaseOneProcessReelExecutor)
    executor._ffprobe_bin = "ffprobe"
    executor._repetition_history_store = None
    result = PhaseOneProcessReelExecutor.run_qa(executor, ex)
    assert isinstance(result, ProcessReelQAResult)
    assert result.passed is False
    details = result.as_payload()
    assert details.get("verdict") == "fail"
    align = details.get("alignment", {})
    assert align.get("verdict") == "fail"


def test_process_reel_qa_passes_baseline_with_technical_format_patched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _process_reel_module,
        "evaluate_format_qa",
        lambda **kwargs: _dummy_passing_format_report(),
    )
    monkeypatch.setattr(
        _process_reel_module,
        "evaluate_overlay_text_fidelity_qa",
        lambda *, script, editing=None: _dummy_passing_overlay(script=script, editing=editing),
    )
    ex = _execution_for_bundle(case_id="well_aligned_baseline")
    executor = object.__new__(PhaseOneProcessReelExecutor)
    executor._ffprobe_bin = "ffprobe"
    executor._repetition_history_store = None
    result = PhaseOneProcessReelExecutor.run_qa(executor, ex)
    assert result.passed is True
    assert result.as_payload().get("verdict") in ("pass", "warn")
