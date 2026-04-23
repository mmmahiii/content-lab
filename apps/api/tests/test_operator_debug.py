from __future__ import annotations

import uuid

from content_lab_api.models.task import Task
from content_lab_api.schemas.operator_debug import (
    ProcessReelOperatorDebugOut,
    build_process_reel_operator_debug,
)
from content_lab_api.schemas.packages import PackageDetailOut
from content_lab_api.schemas.reels import ReelDetailOut
from content_lab_api.schemas.runs import RunDetailOut


def test_build_operator_debug_surfaces_semantic_qa_and_scene_prompt_summaries() -> None:
    summary = {
        "step_outputs": {
            "creative_planning": {
                "scene_plan": {
                    "title": "Test plan",
                    "duration_seconds": 12,
                    "beats": [{"id": "b1"}, {"id": "b2"}],
                },
                "compiled_prompt": {
                    "trace": {
                        "steps": [{"role": "system"}, {"role": "user"}],
                        "summary": "x" * 600,
                    }
                },
            },
            "qa": {
                "passed": True,
                "verdict": "pass",
                "semantic_script": {
                    "verdict": "pass",
                    "findings": [{"code": "hook_length", "outcome": "warn"}],
                },
                "format": {"verdict": "pass"},
                "repetition": {"gate_name": "repetition", "passed": True},
                "alignment": {"verdict": "pass"},
                "checks": [],
            },
            "packaging": {"package_qa": {"passed": True, "message": "ok"}},
        },
        "package": {
            "creative_trace_uri": "s3://content-lab/reels/packages/reel-1/creative_trace.json",
            "creative_trace": {
                "schema_version": "phase_1",
                "artifact_type": "creative_trace",
                "reel_id": "reel-1",
                "run_id": "run-1",
                "generator_selection": {"provider_name": "stub"},
            },
        },
    }
    out = build_process_reel_operator_debug(
        workflow_key="process_reel",
        summary=summary,
        tasks=None,
        expand_debug=False,
    )
    assert out is not None
    assert out.qa is not None
    assert out.qa.semantic_script is not None
    assert out.qa.semantic_script["findings"][0]["code"] == "hook_length"
    assert out.scene_plan_summary is not None
    assert out.scene_plan_summary.beat_count == 2
    assert out.prompt_trace_summary is not None
    assert out.prompt_trace_summary.step_count == 2
    assert out.prompt_trace_summary.excerpt is not None
    assert len(out.prompt_trace_summary.excerpt) <= 500
    assert out.creative_trace is not None
    assert out.creative_trace.storage_uri is not None
    assert out.creative_trace.body is None
    assert out.package_qa is not None
    assert out.package_qa["passed"] is True

    expanded = build_process_reel_operator_debug(
        workflow_key="process_reel",
        summary=summary,
        tasks=None,
        expand_debug=True,
    )
    assert expanded is not None
    assert expanded.scene_plan is not None
    assert expanded.prompt_trace is not None
    assert expanded.creative_trace is not None
    assert expanded.creative_trace.body is not None


def test_build_operator_debug_merges_qa_from_task_when_step_output_missing() -> None:
    task = Task(
        org_id=uuid.uuid4(),
        task_type="qa",
        idempotency_key="qa-key",
        status="succeeded",
        run_id=uuid.uuid4(),
        payload={},
        result={
            "passed": False,
            "verdict": "fail",
            "semantic_script": {"verdict": "fail", "findings": []},
        },
    )
    summary = {"step_outputs": {}}
    out = build_process_reel_operator_debug(
        workflow_key="process_reel",
        summary=summary,
        tasks=[task],
        expand_debug=False,
    )
    assert out is not None
    assert out.qa is not None
    assert out.qa.passed is False


def test_run_detail_out_accepts_operator_debug_field() -> None:
    payload = {
        "id": str(uuid.uuid4()),
        "org_id": str(uuid.uuid4()),
        "workflow_key": "process_reel",
        "flow_trigger": "manual",
        "status": "succeeded",
        "idempotency_key": None,
        "external_ref": None,
        "input_params": {},
        "output_payload": None,
        "run_metadata": {},
        "started_at": None,
        "finished_at": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "tasks": [],
        "task_status_counts": {},
        "outbox": {"events": [], "pending_count": 0, "sent_count": 0, "failed_count": 0},
        "operator_debug": None,
    }
    RunDetailOut.model_validate(payload)


def test_reel_detail_out_accepts_operator_debug_field() -> None:
    payload = {
        "id": str(uuid.uuid4()),
        "org_id": str(uuid.uuid4()),
        "page_id": str(uuid.uuid4()),
        "reel_family_id": str(uuid.uuid4()),
        "origin": "generated",
        "status": "ready",
        "variant_label": "A",
        "external_reel_id": None,
        "metadata": {},
        "approved_at": None,
        "approved_by": None,
        "posted_at": None,
        "posted_by": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "operator_debug": None,
    }
    ReelDetailOut.model_validate(payload)


def test_package_detail_out_accepts_new_fields() -> None:
    payload = {
        "run_id": str(uuid.uuid4()),
        "org_id": str(uuid.uuid4()),
        "status": "succeeded",
        "workflow_key": "process_reel",
        "reel_id": str(uuid.uuid4()),
        "package_root_uri": None,
        "manifest_uri": None,
        "manifest_metadata": {},
        "manifest_download": None,
        "provenance": {},
        "provenance_uri": None,
        "provenance_download": None,
        "creative_trace_uri": None,
        "creative_trace_download": None,
        "operator_debug": None,
        "artifacts": [],
        "outbox_notification": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    PackageDetailOut.model_validate(payload)


def test_process_reel_operator_debug_model_round_trip() -> None:
    model = ProcessReelOperatorDebugOut(
        qa=None,
        package_qa={"passed": True},
        creative_trace=None,
        scene_plan=None,
        scene_plan_summary=None,
        prompt_trace=None,
        prompt_trace_summary=None,
    )
    ProcessReelOperatorDebugOut.model_validate(model.model_dump(mode="json"))
