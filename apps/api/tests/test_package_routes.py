from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import Org, Run


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
            "package": {
                "reel_id": str(reel_id),
                "package_root_uri": f"s3://content-lab/reels/packages/{reel_id}",
                "manifest_uri": f"s3://content-lab/reels/packages/{reel_id}/package_manifest.json",
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
                ],
            }
        },
    )
    db_session.add(run)
    db_session.flush()

    response = package_client.get(f"/orgs/{org.id}/packages/{run.id}")

    assert response.status_code == 200
    payload = response.json()
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
    artifacts = {artifact["name"]: artifact for artifact in payload["artifacts"]}
    assert set(artifacts) == {"cover", "final_video"}
    assert artifacts["final_video"]["download"]["url"].startswith(
        f"http://localhost:9000/content-lab/reels/packages/{reel_id}/final_video.mp4?"
    )


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
