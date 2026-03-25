from __future__ import annotations

from datetime import timedelta

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
