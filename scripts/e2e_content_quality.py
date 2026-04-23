#!/usr/bin/env python3
"""Content-quality acceptance: ``process_reel`` with package, semantic QA, and creative trace.

This is the repo’s “good enough to review” gate. It reuses the orchestrator phase-one
harness (fake Runway, deterministic media via FFmpeg, in-memory persistence) and
validates the same contracts as the ``test_process_reel_flow_runs_full_phase_one_*``
and semantic-QA cases.

Run from repo root (recommended)::

  cd apps/orchestrator
  poetry run python ../../scripts/e2e_content_quality.py --mode pass
  poetry run python ../../scripts/e2e_content_quality.py --mode fail

``--mode fail`` uses a known semantically weak script in QA and expects ``qa_failed``,
not a successful package.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from content_lab_creative import ScriptGeneratorPath

# Orchestrator and API types (Poetry venv: apps/orchestrator).
from content_lab_api.services import (
    InMemoryProcessReelRepository,
    ProcessReelExecution,
    ProcessReelPersistenceService,
    ProcessReelQAResult,
)
from content_lab_qa import SemanticScriptQARequest, evaluate_semantic_script

# The parent ``flows`` package re-exports ``process_reel`` (the @flow), so
# ``import ...flows.process_reel`` can bind the Flow object. Load the source module.
process_reel_module = importlib.import_module("content_lab_orchestrator.flows.process_reel")

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWN_REEL_ID = "reel-42"


def _load_orchestrator_test_harness() -> Any:
    """Load ``apps/orchestrator/tests/test_flow.py`` for shared fake Runway/FFmpeg fixtures."""
    path = REPO_ROOT / "apps" / "orchestrator" / "tests" / "test_flow.py"
    spec = importlib.util.spec_from_file_location("content_lab_orchestrator_test_flow_harness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load test harness from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_reel_harness(repository: InMemoryProcessReelRepository) -> None:
    repository.seed_reel(
        reel_id=KNOWN_REEL_ID,
        org_id="org-1",
        page_id="page-7",
        reel_family_id="family-9",
    )


def _build_phase_one_service(
    h: Any,
    tmp_path: Path,
) -> tuple[
    ProcessReelPersistenceService,
    Any,
    Any,
    Any,
    Any,
]:
    """Mirror ``_install_phase_one_service`` (mocked provider path) without pytest."""
    repository = InMemoryProcessReelRepository()
    _seed_reel_harness(repository)
    storage_client = h.FakeStorageClient()
    clip_bytes = h._build_fixture_clip_bytes(tmp_path)
    asset_resolver = h.FakeProcessReelAssetResolver(
        storage_client=storage_client,
        clip_bytes=clip_bytes,
    )
    executor = h.PhaseOneProcessReelExecutor(
        planning_context_loader=h.FakePlanningContextLoader(),
        asset_resolver=asset_resolver,
        storage_client=storage_client,
        package_layout=process_reel_module.CanonicalStorageLayout(bucket="content-lab"),
        temp_root=tmp_path / "phase-one",
        script_generator_path=ScriptGeneratorPath.RULES_PLUS_PROVIDER,
    )
    service = ProcessReelPersistenceService(repository=repository, executor=executor)
    event_sink = h.FakeProcessReelEventSink()
    return service, event_sink, repository, storage_client, asset_resolver


def _build_weak_semantic_fail_service(
    h: Any,
) -> tuple[ProcessReelPersistenceService, Any, InMemoryProcessReelRepository]:
    """Forces semantic QA to fail on a low-signal script while the rest of the flow is healthy."""

    class WeakSemanticExecutor:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def create_creative_plan(self, execution: ProcessReelExecution) -> dict[str, Any]:
            self.calls.append("creative_planning")
            strong = h._strong_creative_output()
            return {
                **strong,
                "script_generation": {
                    "generator_path": "rules_plus_provider",
                    "provider_name": "rules_provider",
                    "metadata": {},
                },
                "script_lint": {"outcome": "pass", "passed": True, "findings": []},
                "primary_asset_request": {
                    "asset_class": "clip",
                    "provider": "runway",
                    "model": "gen4.5",
                    "prompt": "ok",
                    "scene_plan": {},
                    "compiled_prompt": {},
                    "prompt_trace": {},
                    "duration_seconds": 12,
                    "fps": 24,
                    "ratio": "9:16",
                    "motion": {},
                    "reference_asset_ids": [],
                    "request_context": {},
                },
            }

        def resolve_assets(self, execution: ProcessReelExecution) -> dict[str, Any]:
            self.calls.append("asset_resolution")
            return {
                "asset_key_hash": "asset-key-hash",
                "policy": {},
                "storage_uri": "memory://assets/source.mp4",
                "provider_job": {"provider": "runway", "status": "succeeded"},
                "provider_job_id": "provider-1",
            }

        def edit_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
            self.calls.append("editing")
            return {
                "edit_id": f"edit-{execution.reel_id}",
                "template_version": "basic_vertical_v1",
                "final_video_path": "/tmp/final_video.mp4",
                "final_video_uri": "file:///tmp/final_video.mp4",
                "cover_path": "/tmp/cover.png",
                "cover_uri": "file:///tmp/cover.png",
                "timeline_uri": "file:///tmp/timeline.json",
            }

        def run_qa(self, execution: ProcessReelExecution) -> ProcessReelQAResult:
            self.calls.append("qa")
            weak_script = {
                "hook_text": "Quick fix:",
                "duration_seconds": 12,
                "spoken_script": [
                    {"start_seconds": 0, "end_seconds": 4, "narration": "Follow for more."},
                    {
                        "start_seconds": 4,
                        "end_seconds": 8,
                        "narration": "Comment below if you liked this.",
                    },
                ],
                "overlay_timeline": [
                    {"start_seconds": 0, "end_seconds": 6, "text": "Wow", "emphasis": "hook"},
                    {"start_seconds": 6, "end_seconds": 12, "text": "Ok", "emphasis": "value"},
                ],
                "caption_variants": [{"variant": "short", "text": "ok"}],
            }
            semantic = evaluate_semantic_script(SemanticScriptQARequest(script=weak_script))
            return ProcessReelQAResult(
                passed=False,
                details={
                    "verdict": "fail",
                    "checks": [semantic.as_qa_result().as_payload()],
                    "format": {"verdict": "pass", "message": "", "failure_reasons": []},
                    "semantic_script": {
                        "verdict": semantic.verdict.value,
                        "message": semantic.message,
                        "failure_reasons": list(semantic.failure_reasons),
                        "findings": [
                            finding.model_dump(mode="json") for finding in semantic.findings
                        ],
                    },
                },
            )

        def package_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
            raise AssertionError("packaging should not run for semantically failed reel")

    repository = InMemoryProcessReelRepository()
    _seed_reel_harness(repository)
    executor = WeakSemanticExecutor()
    service = ProcessReelPersistenceService(repository=repository, executor=cast(Any, executor))
    event_sink = h.FakeProcessReelEventSink()
    return service, event_sink, repository


def _assert_pass(result: dict[str, Any], storage_client: Any) -> None:
    if result.get("reel_status") != "ready":
        raise SystemExit(
            f"expected reel_status=ready, got {result.get('reel_status')!r} "
            f"(run_status={result.get('run_status')!r})"
        )
    if result.get("run_status") != "succeeded":
        raise SystemExit(f"expected run_status=succeeded, got {result.get('run_status')!r}")

    package = cast(dict[str, Any], result["package"])
    manifest = cast(dict[str, Any], package["manifest"])
    if manifest.get("complete") is not True:
        raise SystemExit("package manifest is not complete")
    package_qa = cast(dict[str, Any], package.get("package_qa", {}))
    if package_qa.get("passed") is not True:
        raise SystemExit("package_qa did not pass")

    pkg_payload = package
    creative_trace = cast(dict[str, Any] | None, pkg_payload.get("creative_trace"))
    if creative_trace is None:
        raise SystemExit("expected creative_trace on the terminal package payload")
    for key in (
        "generator_selection",
        "script_lint",
        "scene_plan",
        "prompt_trace",
    ):
        if key not in creative_trace:
            raise SystemExit(f"creative_trace missing {key!r}")

    step_outputs = cast(dict[str, Any], result.get("step_outputs", {}))
    qa_out = cast(dict[str, Any], step_outputs.get("qa", {}))
    semantic = cast(dict[str, Any], qa_out.get("semantic_script", {}))
    if semantic.get("verdict") != "pass":
        raise SystemExit(f"expected semantic_script verdict=pass, got {semantic!r}")
    if semantic.get("findings") not in (None, []):
        raise SystemExit("expected no semantic_script findings in pass mode")

    reel_id = str(result.get("reel_id", ""))
    trace_key = f"s3://content-lab/reels/packages/{reel_id}/creative_trace.json"
    if trace_key not in storage_client.objects:
        raise SystemExit(
            f"expected creative trace object in fake storage: missing {trace_key!r} "
            f"(have {len(storage_client.objects)} objects)"
        )


def _assert_fail(result: dict[str, Any], event_sink: Any) -> None:
    if result.get("reel_status") != "qa_failed":
        raise SystemExit(
            f"expected reel_status=qa_failed in fail mode, got {result.get('reel_status')!r}"
        )
    qa = cast(dict[str, Any], cast(dict[str, Any], result.get("step_outputs", {})).get("qa", {}))
    semantic = cast(dict[str, Any], qa.get("semantic_script", {}))
    if semantic.get("verdict") != "fail":
        raise SystemExit(f"expected semantic_script fail in fail mode, got {semantic!r}")
    codes = [
        cast(str, f.get("code", "")) for f in cast(list[dict[str, Any]], semantic.get("findings", []))
    ]
    if "incomplete_hook" not in codes:
        raise SystemExit(f"expected incomplete_hook in semantic findings, got {codes!r}")
    if not any(
        cast(dict[str, Any], e).get("event_type") == "process_reel.failed" for e in event_sink.events
    ):
        raise SystemExit("expected a terminal process_reel.failed outbox event in fail mode")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("pass", "fail"),
        default="pass",
        help="pass: full happy path with real semantic + creative-trace checks; fail: semantic QA blocks readiness",
    )
    args = parser.parse_args(argv)

    h = _load_orchestrator_test_harness()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        if args.mode == "pass":
            service, event_sink, _repo, storage_client, _resolver = _build_phase_one_service(
                h, tmp_path=tmp_path
            )
        else:
            service, event_sink, _repo = _build_weak_semantic_fail_service(h)

        with (
            patch.object(
                process_reel_module, "build_process_reel_runtime", lambda: service
            ),
            patch.object(
                process_reel_module, "build_process_reel_event_sink", lambda: event_sink
            ),
        ):
            result = process_reel_module.process_reel(reel_id=KNOWN_REEL_ID, dry_run=False)

        if args.mode == "pass":
            if not event_sink.events:
                raise SystemExit("expected at least one terminal outbox event")
            if cast(dict[str, Any], event_sink.events[0]).get("event_type") != "process_reel.package_ready":
                raise SystemExit(
                    "expected process_reel.package_ready terminal event in pass mode, "
                    f"got {event_sink.events!r}"
                )
            _assert_pass(result, storage_client)
        else:
            _assert_fail(result, event_sink)

    print("e2e_content_quality: OK", f"(mode={args.mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
