from __future__ import annotations

from uuid import uuid4

import pytest

from content_lab_runs import (
    DuplicateIdempotencyKeyError,
    IdempotentResult,
    RunRowSpec,
    RunStatus,
    TaskRowSpec,
    TaskStatus,
    build_task_idempotency_key,
    task_status_for_run_status,
)


def test_build_task_idempotency_key_is_stable_for_equivalent_payloads() -> None:
    key_one = build_task_idempotency_key(
        "process_reel.validate",
        payload={"reel_id": "reel-1", "options": {"dry_run": True, "step": 1}},
    )
    key_two = build_task_idempotency_key(
        "process_reel.validate",
        payload={"options": {"step": 1, "dry_run": True}, "reel_id": "reel-1"},
    )

    assert key_one == key_two
    assert key_one.startswith("process_reel.validate:")


def test_build_task_idempotency_key_supports_readable_token_shape() -> None:
    assert build_task_idempotency_key("asset.generate", token="abc123") == "asset.generate:abc123"


def test_task_row_spec_state_helpers_cover_retry_path() -> None:
    task = TaskRowSpec(
        org_id=uuid4(),
        task_type="provider.submit",
        idempotency_key="provider.submit:job-1",
        status=TaskStatus.QUEUED,
        payload={"provider": "runway"},
    )

    running = task.running()
    retrying = running.retrying(result={"attempt": 1, "reason": "timeout"})
    succeeded = retrying.succeeded(result={"external_ref": "rw-123"})

    assert running.status is TaskStatus.RUNNING
    assert retrying.status is TaskStatus.RETRYING
    assert retrying.result == {"attempt": 1, "reason": "timeout"}
    assert succeeded.status is TaskStatus.SUCCEEDED
    assert succeeded.result == {"external_ref": "rw-123"}
    assert succeeded.is_terminal is True


def test_run_and_task_specs_export_row_values() -> None:
    org_id = uuid4()
    run = RunRowSpec(
        org_id=org_id,
        workflow_key="daily_reel_factory",
        flow_trigger="manual",
        status=RunStatus.QUEUED,
        input_params={"page_limit": 2},
        run_metadata={"submitted_via": "api"},
    )
    task = TaskRowSpec(
        org_id=org_id,
        run_id="run-1",
        task_type="plan_reels",
        idempotency_key="plan_reels:batch-1",
        status=TaskStatus.QUEUED,
        payload={"page_limit": 2},
    )

    assert run.as_row()["status"] == "queued"
    assert task.as_row()["status"] == "queued"
    assert task.as_row()["run_id"] == "run-1"


def test_task_status_for_run_status_maps_cancelled_to_skipped() -> None:
    assert task_status_for_run_status(RunStatus.CANCELLED) is TaskStatus.SKIPPED


def test_duplicate_idempotency_key_error_exposes_clean_fields() -> None:
    error = DuplicateIdempotencyKeyError(record_type="task", idempotency_key="task:dup-1")

    assert str(error) == "duplicate task idempotency key: task:dup-1"
    assert error.record_type == "task"
    assert error.idempotency_key == "task:dup-1"


def test_idempotent_result_reports_duplicate_flag() -> None:
    created = IdempotentResult(record="run-1", created=True)
    duplicate = IdempotentResult(record="run-1", created=False)

    assert created.duplicate is False
    assert duplicate.duplicate is True


def test_build_task_idempotency_key_requires_single_strategy() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        build_task_idempotency_key("provider.submit")

    with pytest.raises(ValueError, match="exactly one"):
        build_task_idempotency_key(
            "provider.submit",
            payload={"provider": "runway"},
            token="runway-job-1",
        )
