"""Quick Reel "Send to Review" (PostgreSQL; skipped when it is not running)."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import Asset, AuditLog, Org, Page, PageKind, Reel, ReelFamily
from content_lab_api.routes import api_router
from content_lab_creative.generation import (
    BranchGenerationRequest,
    BranchSelection,
    CreativePageContext,
    HookGenerationRequest,
    compose_reel,
    fallback_branches,
    fallback_hooks,
)

PATH = "/orgs/{org}/pages/{page}/quick-reel/reels"


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def scope(db_session: Session) -> dict[str, Any]:
    org = Org(name="Quick Org", slug=f"quick-{uuid.uuid4().hex[:8]}")
    other_org = Org(name="Other Org", slug=f"other-{uuid.uuid4().hex[:8]}")
    db_session.add_all([org, other_org])
    db_session.flush()
    page = Page(
        org_id=org.id,
        platform="instagram",
        display_name="Crispy Kitchen",
        external_page_id=f"ig-{uuid.uuid4().hex[:8]}",
        kind=PageKind.OWNED.value,
        metadata_={"niche": "cooking"},
    )
    disclosed = Page(
        org_id=org.id,
        platform="instagram",
        display_name="Partner Kitchen",
        external_page_id=f"ig-{uuid.uuid4().hex[:8]}",
        kind=PageKind.OWNED.value,
        metadata_={
            "niche": "cooking",
            "constraints": {"required_disclosures": ["Paid partnership"]},
        },
    )
    other_page = Page(
        org_id=other_org.id,
        platform="instagram",
        display_name="Elsewhere",
        external_page_id=f"ig-{uuid.uuid4().hex[:8]}",
        kind=PageKind.OWNED.value,
        metadata_={},
    )
    db_session.add_all([page, disclosed, other_page])
    db_session.flush()
    asset = Asset(org_id=org.id, asset_class="image", storage_uri="s3://content-lab/a/basil.png")
    foreign_asset = Asset(
        org_id=other_org.id, asset_class="image", storage_uri="s3://content-lab/b/x.png"
    )
    db_session.add_all([asset, foreign_asset])
    db_session.flush()
    return {
        "org": org.id,
        "page": page.id,
        "disclosed": disclosed.id,
        "other_page": other_page.id,
        "asset": asset.id,
        "foreign_asset": foreign_asset.id,
    }


def _payload(**overrides: Any) -> dict[str, Any]:
    page = CreativePageContext(page_name="Crispy Kitchen", niche="cooking")
    hook = fallback_hooks(HookGenerationRequest(page=page, topic="crispy potatoes"))[0]
    branches = fallback_branches(
        BranchGenerationRequest(page=page, hook=hook, topic="crispy potatoes")
    )
    body: dict[str, Any] = {
        "hook": hook.model_dump(mode="json"),
        "branches": branches.model_dump(mode="json"),
        "selection": {"structure": "mistake_fix", "energy": "dramatic", "ending": "part_two"},
        "duration_seconds": 15,
        "topic": "crispy potatoes",
        "caption": "The crispy potatoes detail most people miss.\n\n#crispypotatoes",
        "generation_source": "fallback",
    }
    body.update(overrides)
    return body


def _url(scope: dict[str, Any], page: str = "page") -> str:
    return PATH.format(org=scope["org"], page=scope[page])


def test_route_is_registered() -> None:
    paths = {getattr(route, "path", "") for route in api_router.routes}
    assert "/orgs/{org_id}/pages/{page_id}/quick-reel/reels" in paths


def test_send_creates_a_ready_reel_in_the_pages_quick_reel_family(
    client: TestClient, scope: dict[str, Any], db_session: Session
) -> None:
    response = client.post(
        _url(scope),
        json=_payload(
            visuals=[{"asset_id": str(scope["asset"]), "fit": "cutout"}],
            render={
                "render_id": "abc123def4567890abcd",
                "duration_seconds": 16,
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "overlay_trace_status": "pass",
            },
        ),
        headers={"X-Actor-Id": "operator:quick"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["origin"] == "generated"
    assert body["page_id"] == str(scope["page"])
    assert body["variant_label"] == "quick:mistake_fix/dramatic/part_two"
    stored = body["metadata"]["quick_reel"]
    assert body["metadata"]["source"] == "quick_reel"
    assert stored["caption"].startswith("The crispy potatoes detail")
    assert stored["visuals"] == [{"asset_id": str(scope["asset"]), "fit": "cutout"}]
    assert stored["render"]["overlay_trace_status"] == "pass"
    assert stored["qa"]["status"] == "not_run"
    assert stored["sent_by"] == "operator:quick"

    family = db_session.get(ReelFamily, uuid.UUID(body["reel_family_id"]))
    assert family is not None
    assert family.name == "Quick Reel"
    assert family.metadata_ == {"mode": "explore", "source": "quick_reel"}
    actions = {
        row.action
        for row in db_session.query(AuditLog).filter(AuditLog.org_id == scope["org"]).all()
    }
    assert {"reel.created", "reel_family.created"} <= actions


def test_stored_timeline_is_recomposed_by_the_server(
    client: TestClient, scope: dict[str, Any]
) -> None:
    payload = _payload()
    response = client.post(_url(scope), json=payload)
    assert response.status_code == 201, response.text
    stored = response.json()["metadata"]["quick_reel"]["composed"]

    from content_lab_creative.generation import BranchSet, HookCandidate

    expected = compose_reel(
        hook=HookCandidate.model_validate(payload["hook"]),
        branches=BranchSet.model_validate(payload["branches"]),
        selection=BranchSelection.model_validate(payload["selection"]),
        duration_seconds=15,
    ).model_dump(mode="json")
    assert stored == expected
    assert stored["pace"] == "dramatic"
    assert stored["ending_style"] == "cliffhanger"


def test_reel_shows_in_the_review_queue_and_can_be_approved(
    client: TestClient, scope: dict[str, Any]
) -> None:
    reel_id = client.post(_url(scope), json=_payload()).json()["id"]
    queue = client.get(
        f"/orgs/{scope['org']}/pages/{scope['page']}/reels", params={"status": "ready"}
    )
    assert queue.status_code == 200
    assert reel_id in [row["id"] for row in queue.json()]

    approved = client.post(
        f"/orgs/{scope['org']}/pages/{scope['page']}/reels/{reel_id}/approve",
        headers={"X-Actor-Id": "operator:reviewer"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved_by"] == "operator:reviewer"


def test_later_sends_reuse_the_family(
    client: TestClient, scope: dict[str, Any], db_session: Session
) -> None:
    first = client.post(_url(scope), json=_payload()).json()
    second = client.post(
        _url(scope),
        json=_payload(selection={"structure": "breakdown", "energy": "chill", "ending": "reveal"}),
    ).json()
    assert first["reel_family_id"] == second["reel_family_id"]
    assert first["id"] != second["id"]
    families = db_session.query(ReelFamily).filter(ReelFamily.page_id == scope["page"]).all()
    assert len(families) == 1


def test_retry_with_the_same_client_request_id_returns_the_same_reel(
    client: TestClient, scope: dict[str, Any], db_session: Session
) -> None:
    request_id = str(uuid.uuid4())
    first = client.post(_url(scope), json=_payload(client_request_id=request_id))
    retry = client.post(_url(scope), json=_payload(client_request_id=request_id))
    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]
    assert db_session.query(Reel).filter(Reel.org_id == scope["org"]).count() == 1


def test_page_disclosure_replaces_the_closing_overlay(
    client: TestClient, scope: dict[str, Any]
) -> None:
    response = client.post(_url(scope, "disclosed"), json=_payload())
    assert response.status_code == 201, response.text
    last = response.json()["metadata"]["quick_reel"]["composed"]["overlay_timeline"][-1]
    assert last == {**last, "emphasis": "disclosure", "text": "Paid partnership"}


def test_rejects_unknown_choices_and_foreign_assets(
    client: TestClient, scope: dict[str, Any]
) -> None:
    bad_choice = client.post(
        _url(scope),
        json=_payload(selection={"structure": "nope", "energy": "chill", "ending": "reveal"}),
    )
    assert bad_choice.status_code == 422
    assert "unknown structure option" in bad_choice.json()["detail"]

    foreign = client.post(
        _url(scope), json=_payload(visuals=[{"asset_id": str(scope["foreign_asset"])}])
    )
    assert foreign.status_code == 422
    assert "Unknown asset" in foreign.json()["detail"]

    blank = client.post(_url(scope), json=_payload(caption=""))
    assert blank.status_code == 422


def test_page_outside_the_org_is_not_found(client: TestClient, scope: dict[str, Any]) -> None:
    response = client.post(_url(scope, "other_page"), json=_payload())
    assert response.status_code == 404
    missing_org = client.post(PATH.format(org=uuid.uuid4(), page=scope["page"]), json=_payload())
    assert missing_org.status_code == 404
