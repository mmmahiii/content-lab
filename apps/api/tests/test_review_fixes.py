"""Regression tests for the 2026-11-25 end-to-end run / route review fixes (needs Postgres)."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db, get_llm_client
from content_lab_api.main import app
from content_lab_api.models import Asset, AssetGenParam, AssetPack, Org, Page, PageKind, Run
from content_lab_api.routes import runs as runs_route
from content_lab_api.services import asset_packs as asset_pack_service


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_llm_client] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def scope(db_session: Session) -> dict[str, uuid.UUID]:
    org = Org(name="Review Org", slug=f"review-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    page = Page(
        org_id=org.id,
        platform="instagram",
        display_name="Review Page",
        external_page_id=f"ig-{uuid.uuid4().hex[:8]}",
        kind=PageKind.OWNED.value,
        metadata_={},
    )
    db_session.add(page)
    db_session.flush()
    return {"org_id": org.id, "page_id": page.id}


def _create_plan(client: TestClient, scope: dict[str, uuid.UUID]) -> dict[str, Any]:
    response = client.post(f"/orgs/{scope['org_id']}/pages/{scope['page_id']}/idea-plans")
    assert response.status_code == 201, response.text
    return response.json()


def test_idea_plans_are_labelled_as_idea_plans(
    client: TestClient, scope: dict[str, uuid.UUID]
) -> None:
    plan = _create_plan(client, scope)
    assert plan["workflow_key"] == "idea_plan"
    assert plan["output_payload"]["plans"][0]["id"] == plan["id"]
    assert plan["output_payload"]["plan"]["generation"]["source"] == "template"


def test_failed_launch_does_not_burn_the_plan(
    client: TestClient,
    scope: dict[str, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _create_plan(client, scope)
    url = (
        f"/orgs/{scope['org_id']}/pages/{scope['page_id']}/idea-plans/{plan['id']}/generate-package"
    )

    def _boom(**_: object) -> dict[str, object]:
        raise RuntimeError("orchestrator unavailable")

    monkeypatch.setattr(runs_route, "_launch_process_reel_flow", _boom)
    failed = client.post(url, json={"generation_mode": "smoke_test"})
    assert failed.status_code == 500

    monkeypatch.setattr(runs_route, "_launch_process_reel_flow", lambda **_: {"pid": 4242})
    retried = client.post(url, json={"generation_mode": "smoke_test"})
    assert retried.status_code == 201, retried.text
    retried_id = retried.json()["id"]
    assert retried.json()["external_ref"] == "local-process:4242"

    # A live run is returned as-is instead of rendering a duplicate.
    again = client.post(url, json={"generation_mode": "smoke_test"})
    assert again.json()["id"] == retried_id
    # force_new_package still creates a new run.
    forced = client.post(url, json={"generation_mode": "smoke_test", "force_new_package": True})
    assert forced.status_code == 201
    assert forced.json()["id"] != retried_id


def test_package_endpoint_reports_not_ready_while_running(
    client: TestClient, db_session: Session, scope: dict[str, uuid.UUID]
) -> None:
    run = Run(
        org_id=scope["org_id"],
        workflow_key="process_reel",
        flow_trigger="manual",
        status="running",
        input_params={"page_id": str(scope["page_id"])},
    )
    db_session.add(run)
    db_session.flush()
    response = client.get(f"/orgs/{scope['org_id']}/packages/{run.id}")
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "Package not ready yet",
        "run_status": "running",
    }

    run.status = "succeeded"
    db_session.flush()
    assert client.get(f"/orgs/{scope['org_id']}/packages/{run.id}").status_code == 404


def test_page_runs_are_paginated(
    client: TestClient, db_session: Session, scope: dict[str, uuid.UUID]
) -> None:
    for index in range(3):
        db_session.add(
            Run(
                org_id=scope["org_id"],
                workflow_key="process_reel",
                flow_trigger="manual",
                status="queued",
                input_params={"page_id": str(scope["page_id"]), "n": index},
            )
        )
    db_session.flush()
    base = f"/orgs/{scope['org_id']}/pages/{scope['page_id']}/runs"
    assert len(client.get(base).json()) == 3
    first = client.get(base, params={"limit": 2}).json()
    rest = client.get(base, params={"limit": 2, "offset": 2}).json()
    assert len(first) == 2 and len(rest) == 1
    assert {r["id"] for r in first}.isdisjoint({r["id"] for r in rest})
    assert client.get(base, params={"limit": 0}).status_code == 422


def test_asset_detail_works_with_several_generation_param_rows(
    client: TestClient, db_session: Session, scope: dict[str, uuid.UUID]
) -> None:
    asset = Asset(
        org_id=scope["org_id"],
        asset_class="clip",
        storage_uri="s3://content-lab/assets/derived/multi-seq.mp4",
        source="runway",
        metadata_={},
    )
    db_session.add(asset)
    db_session.flush()
    for seq in range(3):
        db_session.add(
            AssetGenParam(
                org_id=scope["org_id"],
                asset_id=asset.id,
                seq=seq,
                asset_key_hash=f"hash-{seq}",
                canonical_params={"seq": seq},
            )
        )
    db_session.flush()
    response = client.get(f"/orgs/{scope['org_id']}/assets/{asset.id}")
    assert response.status_code == 200, response.text
    assert response.json()["canonical_params"] == {"seq": 2}


def test_failed_pack_generation_marks_pack_failed_and_allows_retry(
    client: TestClient,
    db_session: Session,
    scope: dict[str, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = scope["org_id"]
    planned = client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Fragile kit",
            "niche": "coffee shop marketing",
            "requested_asset_count": 1,
            "asset_mix": {"hook_text": 1},
        },
    )
    assert planned.status_code == 201, planned.text
    pack_id = planned.json()["asset_pack"]["id"]
    assert client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/approve", json={}).status_code == 200

    def _explode(**_: object) -> None:
        raise RuntimeError("acquisition service down")

    monkeypatch.setattr(asset_pack_service, "evaluate_acquisition_before_generation", _explode)
    with pytest.raises(RuntimeError):
        client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/generate", json={})

    pack = db_session.get(AssetPack, uuid.UUID(pack_id))
    assert pack is not None
    db_session.refresh(pack)
    assert pack.status == "failed"

    monkeypatch.undo()
    # From FAILED the plan can be regenerated...
    regenerated = client.post(
        f"/orgs/{org_id}/asset-packs/{pack_id}/regenerate-plan",
        json={
            "niche": "coffee shop marketing",
            "requested_asset_count": 1,
            "asset_mix": {"hook_text": 1},
        },
    )
    assert regenerated.status_code == 200, regenerated.text
    db_session.refresh(pack)
    assert pack.status == "planned"  # a new plan needs approving again
    assert client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/approve", json={}).status_code == 200
    assert client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/generate", json={}).status_code == 201

    # ...or generation can be retried straight from FAILED.
    pack.status = "failed"
    db_session.flush()
    retried = client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/generate", json={})
    assert retried.status_code == 201, retried.text
    db_session.refresh(pack)
    assert pack.status != "failed"
