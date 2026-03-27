from __future__ import annotations

from datetime import timedelta

from content_lab_runs import TaskStatus
from content_lab_worker.actors.provider import (
    build_provider_submission_task,
    get_provider_sweep_threshold,
    is_terminal_provider_job_status,
)


def test_build_provider_submission_task_carries_provider_job_linkage() -> None:
    task = build_provider_submission_task(
        org_id="org-1",
        provider=" Runway ",
        external_ref=" runway-gen45:hash-1 ",
        asset_id="asset-1",
        provider_job_id="provider-job-1",
        provider_job_status="RUNNING",
        payload={"attempt": 1},
    )

    assert task.task_type == "provider.submit"
    assert task.payload == {
        "provider": "runway",
        "external_ref": "runway-gen45:hash-1",
        "provider_job_status": "running",
        "asset_id": "asset-1",
        "provider_job_id": "provider-job-1",
        "attempt": 1,
    }


def test_build_provider_submission_task_records_budget_warning() -> None:
    task = build_provider_submission_task(
        org_id="org-1",
        provider="runway",
        external_ref="runway-gen45:hash-2",
        submission_cost_usd=8.0,
        budget_policy={"daily_usd_limit": 20.0, "per_run_usd_limit": 8.0},
        budget_usage={"daily_spent_usd": 6.0, "daily_committed_usd": 6.0},
    )

    budget_guardrail = task.payload["budget_guardrail"]
    assert task.status == TaskStatus.QUEUED
    assert budget_guardrail == {
        "allowed": True,
        "status": "warn",
        "detail": "Approved 1 units, but only 0.00 USD remains before today's budget guardrail is fully consumed.",
        "action": "proceed",
        "scope": "provider_submission",
        "requested_units": 1,
        "approved_units": 1,
        "unit_cost_usd": 8.0,
        "requested_cost_usd": 8.0,
        "approved_cost_usd": 8.0,
        "spent_usd": 6.0,
        "committed_usd": 6.0,
        "reserved_usd": 12.0,
        "remaining_before_usd": 8.0,
        "remaining_after_usd": 0.0,
        "reasons": ["remaining_budget_below_warning_threshold"],
    }


def test_build_provider_submission_task_skips_when_budget_guardrail_blocks_submission() -> None:
    task = build_provider_submission_task(
        org_id="org-1",
        provider="runway",
        external_ref="runway-gen45:hash-3",
        submission_cost_usd=6.0,
        budget_policy={"daily_usd_limit": 10.0, "per_run_usd_limit": 6.0},
        budget_usage={"daily_spent_usd": 7.0},
    )

    assert task.status == TaskStatus.SKIPPED
    assert task.payload["budget_guardrail"]["status"] == "stop"
    assert task.result == {
        "budget_guardrail": task.payload["budget_guardrail"],
        "reason": "Stopped provider_submission: requested 6.00 USD but only 3.00 USD remains in today's budget.",
        "status": "skipped_by_budget_guardrail",
    }


def test_provider_sweep_thresholds_cover_runway_transient_statuses() -> None:
    submitted = get_provider_sweep_threshold(provider="runway", status="submitted")
    retryable = get_provider_sweep_threshold(provider="runway", status="retryable")

    assert submitted is not None
    assert submitted.max_age == timedelta(minutes=15)
    assert retryable is not None
    assert retryable.max_age == timedelta(minutes=10)
    assert get_provider_sweep_threshold(provider="runway", status="FAILED") is None


def test_terminal_provider_job_statuses_are_excluded_from_sweeping() -> None:
    assert is_terminal_provider_job_status(provider="runway", status="succeeded") is True
    assert is_terminal_provider_job_status(provider="runway", status="cancelled") is True
    assert is_terminal_provider_job_status(provider="runway", status="running") is False
