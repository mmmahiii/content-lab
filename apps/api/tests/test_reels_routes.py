from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import (
    AuditLog,
    GeneratedReelStatus,
    ObservedReelStatus,
    Org,
    Page,
    PageKind,
    Reel,
    ReelFamily,
    ReelOrigin,
)


def _make_page(
    org_id: uuid.UUID, *, platform: str, display_name: str, external_page_id: str
) -> Page:
    return Page(
        org_id=org_id,
        platform=platform,
        display_name=display_name,
        external_page_id=external_page_id,
        kind=PageKind.OWNED.value,
        metadata_={},
    )


@pytest.fixture
def reels_client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_reel_scope(db_session: Session) -> dict[str, uuid.UUID]:
    org_one = Org(name="Primary Org", slug=f"primary-{uuid.uuid4().hex[:8]}")
    org_two = Org(name="Secondary Org", slug=f"secondary-{uuid.uuid4().hex[:8]}")
    db_session.add_all([org_one, org_two])
    db_session.flush()

    primary_page = _make_page(
        org_one.id,
        platform="instagram",
        display_name="Primary Page",
        external_page_id="ig-primary-001",
    )
    secondary_page = _make_page(
        org_one.id,
        platform="instagram",
        display_name="Secondary Page",
        external_page_id="ig-secondary-001",
    )
    other_org_page = _make_page(
        org_two.id,
        platform="instagram",
        display_name="Other Org Page",
        external_page_id="ig-other-001",
    )
    db_session.add_all([primary_page, secondary_page, other_org_page])
    db_session.flush()

    family = ReelFamily(
        org_id=org_one.id,
        page_id=primary_page.id,
        name="Primary family",
        metadata_={"mode": "explore"},
    )
    other_page_family = ReelFamily(
        org_id=org_one.id,
        page_id=secondary_page.id,
        name="Other page family",
        metadata_={"mode": "exploit"},
    )
    other_org_family = ReelFamily(
        org_id=org_two.id,
        page_id=other_org_page.id,
        name="Other org family",
        metadata_={"mode": "mutation"},
    )
    db_session.add_all([family, other_page_family, other_org_family])
    db_session.flush()

    return {
        "org_id": org_one.id,
        "other_org_id": org_two.id,
        "page_id": primary_page.id,
        "other_page_id": secondary_page.id,
        "other_org_page_id": other_org_page.id,
        "family_id": family.id,
        "other_page_family_id": other_page_family.id,
        "other_org_family_id": other_org_family.id,
    }


def test_reel_create_get_and_list_are_scoped_and_audited(
    reels_client: TestClient,
    db_session: Session,
    seeded_reel_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_reel_scope["org_id"]
    page_id = seeded_reel_scope["page_id"]
    family_id = seeded_reel_scope["family_id"]

    create_response = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels",
        json={
            "variant_label": " A ",
            "status": "draft",
            "metadata": {"editor_template": "hook-fast-cut"},
        },
        headers={"X-Actor-Id": "operator:test-user"},
    )

    assert create_response.status_code == 201
    created = create_response.json()
    reel_id = created["id"]
    assert created["org_id"] == str(org_id)
    assert created["page_id"] == str(page_id)
    assert created["reel_family_id"] == str(family_id)
    assert created["origin"] == "generated"
    assert created["status"] == "draft"
    assert created["variant_label"] == "A"
    assert created["metadata"] == {"editor_template": "hook-fast-cut"}
    assert created["approved_at"] is None
    assert created["posted_at"] is None

    observed = Reel(
        org_id=org_id,
        reel_family_id=family_id,
        origin=ReelOrigin.OBSERVED.value,
        status=ObservedReelStatus.ACTIVE.value,
        external_reel_id="obs-reel-001",
        metadata_={"source": "competitor_ingest"},
    )
    db_session.add(observed)
    db_session.flush()
    db_session.expire_all()

    list_response = reels_client.get(f"/orgs/{org_id}/pages/{page_id}/reels")
    family_list_response = reels_client.get(
        f"/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels"
    )
    generated_only_response = reels_client.get(
        f"/orgs/{org_id}/pages/{page_id}/reels?origin=generated"
    )
    observed_only_response = reels_client.get(
        f"/orgs/{org_id}/pages/{page_id}/reels?origin=observed&status=active"
    )
    get_response = reels_client.get(f"/orgs/{org_id}/pages/{page_id}/reels/{reel_id}")

    assert list_response.status_code == 200
    assert family_list_response.status_code == 200
    assert generated_only_response.status_code == 200
    assert observed_only_response.status_code == 200
    assert get_response.status_code == 200

    all_reels = list_response.json()
    assert [item["origin"] for item in all_reels] == ["observed", "generated"]
    assert {item["id"] for item in family_list_response.json()} == {reel_id, str(observed.id)}
    assert [item["id"] for item in generated_only_response.json()] == [reel_id]
    assert [item["id"] for item in observed_only_response.json()] == [str(observed.id)]
    assert get_response.json()["variant_label"] == "A"

    audit_rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.org_id == org_id, AuditLog.resource_id == reel_id)
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    assert [row.action for row in audit_rows] == ["reel.created"]
    assert all(row.resource_type == "reel" for row in audit_rows)
    assert all(row.actor_id == "operator:test-user" for row in audit_rows)


def test_reel_create_rejects_invalid_generated_payloads(
    reels_client: TestClient,
    seeded_reel_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_reel_scope["org_id"]
    page_id = seeded_reel_scope["page_id"]
    family_id = seeded_reel_scope["family_id"]

    observed_origin_response = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels",
        json={"origin": "observed", "variant_label": "obs", "metadata": {}},
    )
    external_id_response = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels",
        json={"variant_label": "A", "external_reel_id": "external-123", "metadata": {}},
    )
    reserved_metadata_response = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels",
        json={
            "variant_label": "B",
            "metadata": {"review": {"approved_by": "operator:test-user"}},
        },
    )

    assert observed_origin_response.status_code == 422
    assert external_id_response.status_code == 422
    assert reserved_metadata_response.status_code == 422


def test_reel_routes_enforce_org_page_and_family_scoping(
    reels_client: TestClient,
    db_session: Session,
    seeded_reel_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_reel_scope["org_id"]
    other_org_id = seeded_reel_scope["other_org_id"]
    page_id = seeded_reel_scope["page_id"]
    other_page_id = seeded_reel_scope["other_page_id"]
    family_id = seeded_reel_scope["family_id"]

    create_response = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels",
        json={"variant_label": "Scoped", "metadata": {}},
    )
    assert create_response.status_code == 201
    reel_id = create_response.json()["id"]

    wrong_org_create = reels_client.post(
        f"/orgs/{other_org_id}/pages/{page_id}/reel-families/{family_id}/reels",
        json={"variant_label": "Wrong org", "metadata": {}},
    )
    wrong_page_get = reels_client.get(f"/orgs/{org_id}/pages/{other_page_id}/reels/{reel_id}")
    wrong_page_list = reels_client.get(
        f"/orgs/{org_id}/pages/{other_page_id}/reel-families/{family_id}/reels"
    )

    assert wrong_org_create.status_code == 404
    assert wrong_org_create.json()["detail"] == "Page not found"
    assert wrong_page_get.status_code == 404
    assert wrong_page_get.json()["detail"] == "Reel not found"
    assert wrong_page_list.status_code == 404
    assert wrong_page_list.json()["detail"] == "Reel family not found"

    cross_page_reel = Reel(
        org_id=org_id,
        reel_family_id=seeded_reel_scope["other_page_family_id"],
        origin=ReelOrigin.GENERATED.value,
        status=GeneratedReelStatus.READY.value,
        variant_label="Other",
        metadata_={},
    )
    db_session.add(cross_page_reel)
    db_session.flush()

    filtered_response = reels_client.get(
        f"/orgs/{org_id}/pages/{page_id}/reels?family_id={seeded_reel_scope['other_page_family_id']}"
    )
    assert filtered_response.status_code == 200
    assert filtered_response.json() == []


def test_reel_human_review_actions_are_guarded_and_audited(
    reels_client: TestClient,
    db_session: Session,
    seeded_reel_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_reel_scope["org_id"]
    page_id = seeded_reel_scope["page_id"]
    family_id = seeded_reel_scope["family_id"]

    ready_reel = Reel(
        org_id=org_id,
        reel_family_id=family_id,
        origin=ReelOrigin.GENERATED.value,
        status=GeneratedReelStatus.READY.value,
        variant_label="Ready",
        metadata_={},
    )
    archive_reel = Reel(
        org_id=org_id,
        reel_family_id=family_id,
        origin=ReelOrigin.GENERATED.value,
        status=GeneratedReelStatus.READY.value,
        variant_label="Archive",
        metadata_={},
    )
    observed_reel = Reel(
        org_id=org_id,
        reel_family_id=family_id,
        origin=ReelOrigin.OBSERVED.value,
        status=ObservedReelStatus.ACTIVE.value,
        external_reel_id="obs-ready-001",
        metadata_={},
    )
    db_session.add_all([ready_reel, archive_reel, observed_reel])
    db_session.flush()

    approve_response = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{ready_reel.id}/approve",
        headers={"X-Actor-Id": "operator:reviewer"},
    )
    assert approve_response.status_code == 200
    approved = approve_response.json()
    assert approved["status"] == "ready"
    assert approved["approved_by"] == "operator:reviewer"
    assert approved["approved_at"] is not None

    repeat_approve = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{ready_reel.id}/approve"
    )
    assert repeat_approve.status_code == 409
    assert repeat_approve.json()["detail"] == "Reel has already been approved"

    mark_posted_response = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{ready_reel.id}/mark-posted",
        headers={"X-Actor-Id": "operator:publisher"},
    )
    assert mark_posted_response.status_code == 200
    posted = mark_posted_response.json()
    assert posted["status"] == "posted"
    assert posted["posted_by"] == "operator:publisher"
    assert posted["posted_at"] is not None

    invalid_after_posted = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{ready_reel.id}/archive"
    )
    assert invalid_after_posted.status_code == 409
    assert invalid_after_posted.json()["detail"] == "Only ready generated reels can be archived"

    archive_response = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{archive_reel.id}/archive",
        headers={"X-Actor-Id": "operator:reviewer"},
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"

    invalid_after_archived = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{archive_reel.id}/mark-posted"
    )
    assert invalid_after_archived.status_code == 409
    assert (
        invalid_after_archived.json()["detail"] == "Only ready generated reels can be marked posted"
    )

    observed_approve = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{observed_reel.id}/approve"
    )
    observed_post = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{observed_reel.id}/mark-posted"
    )
    assert observed_approve.status_code == 409
    assert observed_post.status_code == 409
    assert (
        observed_approve.json()["detail"] == "Review actions are only allowed for generated reels"
    )
    assert observed_post.json()["detail"] == "Review actions are only allowed for generated reels"

    audit_rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.org_id == org_id)
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .all()
    )
    assert sorted(row.action for row in audit_rows) == [
        "reel.approved",
        "reel.archived",
        "reel.mark_posted",
    ]


def test_reel_review_actions_reject_non_ready_generated_reels(
    reels_client: TestClient,
    db_session: Session,
    seeded_reel_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_reel_scope["org_id"]
    page_id = seeded_reel_scope["page_id"]
    family_id = seeded_reel_scope["family_id"]

    draft_reel = Reel(
        org_id=org_id,
        reel_family_id=family_id,
        origin=ReelOrigin.GENERATED.value,
        status=GeneratedReelStatus.DRAFT.value,
        variant_label="Draft",
        metadata_={},
    )
    db_session.add(draft_reel)
    db_session.flush()

    approve_response = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{draft_reel.id}/approve"
    )
    post_response = reels_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{draft_reel.id}/mark-posted"
    )

    assert approve_response.status_code == 409
    assert approve_response.json()["detail"] == "Only ready generated reels can be approved"
    assert post_response.status_code == 409
    assert post_response.json()["detail"] == "Only ready generated reels can be marked posted"
