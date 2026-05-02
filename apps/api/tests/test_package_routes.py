from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import Org, OutboxEvent, Run, Task
from content_lab_outbox import PROCESS_REEL_PACKAGE_READY_EVENT


@pytest.fixture
def package_client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_get_package_returns_manifest_provenance_and_signed_artifacts(
    db_session: Session,
    package_client: TestClient,
) -> None:
    org = Org(name="Package Org", slug=f"package-org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()

    reel_id = uuid.uuid4()
    run = Run(
        org_id=org.id,
        workflow_key="process_reel",
        status="succeeded",
        input_params={"reel_id": str(reel_id)},
        output_payload={
            "step_outputs": {
                "qa": {
                    "passed": True,
                    "verdict": "pass",
                    "semantic_script": {
                        "verdict": "pass",
                        "findings": [{"code": "package_route_semantic", "outcome": "warn"}],
                    },
                    "format": {"verdict": "pass"},
                    "repetition": {"gate_name": "repetition", "passed": True},
                    "alignment": {"verdict": "pass"},
                    "checks": [],
                },
            },
            "package": {
                "reel_id": str(reel_id),
                "package_root_uri": f"s3://content-lab/reels/packages/{reel_id}",
                "manifest_uri": f"s3://content-lab/reels/packages/{reel_id}/package_manifest.json",
                "creative_trace_uri": f"s3://content-lab/reels/packages/{reel_id}/creative_trace.json",
                "manifest": {
                    "version": 1,
                    "artifact_count": 2,
                },
                "provenance_uri": f"s3://content-lab/reels/packages/{reel_id}/provenance.json",
                "provenance": {
                    "source_run_id": "run-123",
                    "asset_ids": ["asset-1", "asset-2"],
                },
                "artifacts": [
                    {
                        "name": "final_video",
                        "storage_uri": f"s3://content-lab/reels/packages/{reel_id}/final_video.mp4",
                        "kind": "video",
                        "content_type": "video/mp4",
                    },
                    {
                        "name": "cover",
                        "storage_uri": f"s3://content-lab/reels/packages/{reel_id}/cover.png",
                        "kind": "image",
                        "content_type": "image/png",
                    },
                    {
                        "name": "provenance",
                        "storage_uri": f"s3://content-lab/reels/packages/{reel_id}/provenance.json",
                        "content_type": "application/json",
                    },
                    {
                        "name": "creative_trace",
                        "storage_uri": f"s3://content-lab/reels/packages/{reel_id}/creative_trace.json",
                        "content_type": "application/json",
                    },
                ],
            },
        },
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        Task(
            org_id=org.id,
            run_id=run.id,
            task_type="packaging",
            idempotency_key=f"packaging-{run.id}",
            status="succeeded",
            payload={},
            result={"package_qa": {"passed": True}},
        )
    )
    db_session.add(
        OutboxEvent(
            org_id=org.id,
            aggregate_type="run",
            aggregate_id=str(run.id),
            event_type=PROCESS_REEL_PACKAGE_READY_EVENT,
            payload={},
            delivery_status="pending",
            attempt_count=0,
        )
    )
    db_session.flush()

    response = package_client.get(f"/orgs/{org.id}/packages/{run.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("packaged_at") is not None
    assert payload["run_id"] == str(run.id)
    assert payload["org_id"] == str(org.id)
    assert payload["reel_id"] == str(reel_id)
    assert payload["manifest_metadata"] == {"version": 1, "artifact_count": 2}
    assert payload["provenance"] == {
        "source_run_id": "run-123",
        "asset_ids": ["asset-1", "asset-2"],
    }
    assert payload["manifest_download"]["url"].startswith(
        f"http://localhost:9000/content-lab/reels/packages/{reel_id}/package_manifest.json?"
    )
    assert payload["provenance_download"]["url"].startswith(
        f"http://localhost:9000/content-lab/reels/packages/{reel_id}/provenance.json?"
    )
    assert payload["creative_trace_uri"] == (
        f"s3://content-lab/reels/packages/{reel_id}/creative_trace.json"
    )
    assert payload["creative_trace_download"]["url"].startswith(
        f"http://localhost:9000/content-lab/reels/packages/{reel_id}/creative_trace.json?"
    )
    operator_debug = payload.get("operator_debug")
    assert operator_debug is not None
    assert (
        operator_debug["qa"]["semantic_script"]["findings"][0]["code"] == "package_route_semantic"
    )
    artifacts = {artifact["name"]: artifact for artifact in payload["artifacts"]}
    assert set(artifacts) == {"cover", "final_video"}
    assert artifacts["final_video"]["download"]["url"].startswith(
        f"http://localhost:9000/content-lab/reels/packages/{reel_id}/final_video.mp4?"
    )
    on = payload.get("outbox_notification")
    assert on is not None
    assert on.get("is_pending") is True
    assert "pending" in (on.get("message") or "").lower()


def test_get_package_includes_outbox_notification_when_event_sent(
    db_session: Session,
    package_client: TestClient,
) -> None:
    org = Org(name="Outbox Package Org", slug=f"outbox-pkg-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    reel_id = uuid.uuid4()
    run = Run(
        org_id=org.id,
        workflow_key="process_reel",
        status="succeeded",
        input_params={"reel_id": str(reel_id)},
        output_payload={"package": {"manifest": {"version": 1}, "reel_id": str(reel_id)}},
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        OutboxEvent(
            org_id=org.id,
            aggregate_type="run",
            aggregate_id=str(run.id),
            event_type=PROCESS_REEL_PACKAGE_READY_EVENT,
            payload={},
            delivery_status="sent",
            attempt_count=1,
        )
    )
    db_session.flush()

    response = package_client.get(f"/orgs/{org.id}/packages/{run.id}")
    assert response.status_code == 200
    on = response.json()["outbox_notification"]
    assert on["is_pending"] is False
    assert on["is_failed"] is False
    assert "dispatched" in (on.get("message") or "").lower()


def test_get_package_is_org_scoped(
    db_session: Session,
    package_client: TestClient,
) -> None:
    org = Org(name="Primary Package Org", slug=f"pkg-primary-{uuid.uuid4().hex[:8]}")
    other_org = Org(name="Other Package Org", slug=f"pkg-other-{uuid.uuid4().hex[:8]}")
    db_session.add_all([org, other_org])
    db_session.flush()

    run = Run(
        org_id=other_org.id,
        workflow_key="process_reel",
        status="succeeded",
        input_params={},
        output_payload={"package": {"manifest": {"version": 1}}},
    )
    db_session.add(run)
    db_session.flush()

    response = package_client.get(f"/orgs/{org.id}/packages/{run.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Package not found"


def test_get_package_rejects_non_canonical_artifact_uris(
    db_session: Session,
    package_client: TestClient,
) -> None:
    org = Org(name="Canonical Package Org", slug=f"pkg-canon-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()

    reel_id = uuid.uuid4()
    run = Run(
        org_id=org.id,
        workflow_key="process_reel",
        status="succeeded",
        input_params={"reel_id": str(reel_id)},
        output_payload={
            "package": {
                "reel_id": str(reel_id),
                "package_root_uri": f"s3://content-lab/reels/packages/{reel_id}",
                "manifest_uri": f"s3://content-lab/reels/packages/{reel_id}/package_manifest.json",
                "provenance_uri": f"s3://content-lab/reels/packages/{reel_id}/provenance.json",
                "artifacts": [
                    {
                        "name": "final_video",
                        "storage_uri": "s3://content-lab/assets/derived/not-a-package.mp4",
                        "kind": "video",
                        "content_type": "video/mp4",
                    }
                ],
            }
        },
    )
    db_session.add(run)
    db_session.flush()

    response = package_client.get(f"/orgs/{org.id}/packages/{run.id}")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Package metadata is invalid: package artifact URIs are outside the canonical package scope"
    )


def test_get_package_requires_reel_id_when_downloadable_package_uris_exist(
    db_session: Session,
    package_client: TestClient,
) -> None:
    org = Org(name="Package Missing Reel Org", slug=f"pkg-missing-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()

    run = Run(
        org_id=org.id,
        workflow_key="process_reel",
        status="succeeded",
        input_params={},
        output_payload={
            "package": {
                "manifest_uri": "s3://content-lab/reels/packages/reel-123/package_manifest.json",
                "artifacts": [],
            }
        },
    )
    db_session.add(run)
    db_session.flush()

    response = package_client.get(f"/orgs/{org.id}/packages/{run.id}")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Package metadata is invalid: reel_id is required to validate package storage scope"
    )
