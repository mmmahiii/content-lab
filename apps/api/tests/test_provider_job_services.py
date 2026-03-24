from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from content_lab_api.models import Org, ProviderJob, Task
from content_lab_api.services.provider_jobs import (
    record_provider_job_poll,
    record_provider_job_result,
    record_provider_job_submission,
)
from content_lab_assets.providers.runway.jobs import RunwayJobStatus, build_runway_job_external_ref


def test_provider_job_services_persist_submission_poll_and_result_lifecycle(
    db_session: Session,
) -> None:
    org = Org(name="Provider Jobs Org", slug=f"provider-jobs-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()

    task = Task(
        org_id=org.id,
        task_type="asset.generate",
        idempotency_key=f"asset.generate:{uuid.uuid4().hex}",
        status="queued",
    )
    db_session.add(task)
    db_session.flush()

    asset_id = uuid.uuid4()
    asset_key_hash = uuid.uuid4().hex + uuid.uuid4().hex
    external_ref = build_runway_job_external_ref(asset_key_hash=asset_key_hash)

    submitted = record_provider_job_submission(
        db_session,
        org_id=org.id,
        task_id=task.id,
        asset_id=asset_id,
        asset_key="asset-key-1",
        asset_key_hash=asset_key_hash,
        request_payload={"metadata": {"api_key": "secret-value"}},
        provider_payload={
            "provider": "runway",
            "model": "gen4.5",
            "external_ref": external_ref,
        },
        task_status=task.status,
        asset_status="staged",
    )
    running = record_provider_job_poll(
        db_session,
        org_id=org.id,
        provider="runway",
        external_ref=external_ref,
        payload={"job_state": "processing", "bearer": "Bearer secret-token"},
        task_id=task.id,
        asset_id=asset_id,
        task_status="running",
        asset_status="staged",
    )
    succeeded = record_provider_job_result(
        db_session,
        org_id=org.id,
        provider="runway",
        external_ref=external_ref,
        status=RunwayJobStatus.SUCCEEDED,
        payload={"job_state": "complete", "download_url": "https://example.test/video.mp4"},
        task_id=task.id,
        asset_id=asset_id,
        task_status="succeeded",
        asset_status="ready",
    )
    db_session.flush()

    rows = db_session.query(ProviderJob).filter(ProviderJob.org_id == org.id).all()

    assert submitted.id == running.id == succeeded.id
    assert len(rows) == 1
    assert rows[0].status == "succeeded"
    assert rows[0].task_id == task.id
    assert rows[0].metadata_["links"] == {
        "task_id": str(task.id),
        "asset_id": str(asset_id),
    }
    assert rows[0].metadata_["snapshots"]["submission"]["request_payload"]["metadata"][
        "api_key"
    ] == ("***REDACTED***")
    assert rows[0].metadata_["snapshots"]["poll"]["provider_payload"]["bearer"] == (
        "***REDACTED***"
    )
    assert rows[0].metadata_["snapshots"]["result"]["status"] == "succeeded"
    assert [entry["status"] for entry in rows[0].metadata_["history"]] == [
        "submitted",
        "running",
        "succeeded",
    ]
