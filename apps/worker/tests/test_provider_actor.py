from __future__ import annotations

from content_lab_worker.actors.provider import build_provider_submission_task


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
