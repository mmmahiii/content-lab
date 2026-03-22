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
    ReelOrigin,
)


def _make_page(org_id: uuid.UUID, *, platform: str, display_name: str, external_page_id: str) -> Page:
    return Page(
        org_id=org_id,
        platform=platform,
        display_name=display_name,
        external_page_id=external_page_id,
        kind=PageKind.OWNED.value,
        metadata_={},
    )


@pytest.fixture
def reel_families_client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_pages(db_session: Session) -> dict[str, uuid.UUID]:
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

    return {
        "org_id": org_one.id,
        "other_org_id": org_two.id,
        "page_id": primary_page.id,
        "other_page_id": secondary_page.id,
        "other_org_page_id": other_org_page.id,
    }


def test_reel_families_create_list_get_are_page_scoped_and_include_variant_summaries(
    reel_families_client: TestClient,
    db_session: Session,
    seeded_pages: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_pages["org_id"]
    page_id = seeded_pages["page_id"]
    other_page_id = seeded_pages["other_page_id"]

    create_response = reel_families_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reel-families",
        json={
            "name": "High-friction founder hooks",
            "mode": "mutation",
            "metadata": {
                "hypothesis": "Reuse the strongest hook with a sharper second beat.",
                "content_pillar": "operations",
            },
        },
        headers={"X-Actor-Id": "operator:test-user"},
    )

    other_page_response = reel_families_client.post(
        f"/orgs/{org_id}/pages/{other_page_id}/reel-families",
        json={
            "name": "New competitor angle",
            "mode": "explore",
            "metadata": {"hypothesis": "Test an adjacent promise for the same audience."},
        },
    )

    assert create_response.status_code == 201
    assert other_page_response.status_code == 201

    created = create_response.json()
    family_id = created["id"]
    other_family_id = other_page_response.json()["id"]

    assert created["org_id"] == str(org_id)
    assert created["page_id"] == str(page_id)
    assert created["mode"] == "mutation"
    assert created["variant_count"] == 0
    assert created["variants"] == []
    assert created["metadata"] == {
        "hypothesis": "Reuse the strongest hook with a sharper second beat.",
        "content_pillar": "operations",
    }

    db_session.add_all(
        [
            Reel(
                org_id=org_id,
                reel_family_id=uuid.UUID(family_id),
                origin=ReelOrigin.GENERATED.value,
                status=GeneratedReelStatus.READY.value,
                variant_label="A",
                metadata_={"editor_template": "hook-fast-cut"},
            ),
            Reel(
                org_id=org_id,
                reel_family_id=uuid.UUID(family_id),
                origin=ReelOrigin.OBSERVED.value,
                status=ObservedReelStatus.ACTIVE.value,
                external_reel_id="obs-reel-001",
                metadata_={"source": "competitor_ingest"},
            ),
        ]
    )
    db_session.flush()
    db_session.expire_all()

    list_response = reel_families_client.get(f"/orgs/{org_id}/pages/{page_id}/reel-families")
    other_page_list_response = reel_families_client.get(
        f"/orgs/{org_id}/pages/{other_page_id}/reel-families"
    )
    get_response = reel_families_client.get(
        f"/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}"
    )

    assert list_response.status_code == 200
    assert other_page_list_response.status_code == 200
    assert get_response.status_code == 200

    page_families = list_response.json()
    assert [family["id"] for family in page_families] == [family_id]
    assert page_families[0]["variant_count"] == 2
    assert {variant["origin"] for variant in page_families[0]["variants"]} == {
        "generated",
        "observed",
    }

    assert [family["id"] for family in other_page_list_response.json()] == [other_family_id]

    loaded = get_response.json()
    variants_by_origin = {variant["origin"]: variant for variant in loaded["variants"]}
    assert loaded["name"] == "High-friction founder hooks"
    assert loaded["mode"] == "mutation"
    assert loaded["variant_count"] == 2
    assert variants_by_origin["generated"]["status"] == "ready"
    assert variants_by_origin["generated"]["variant_label"] == "A"
    assert variants_by_origin["observed"]["status"] == "active"
    assert variants_by_origin["observed"]["external_reel_id"] == "obs-reel-001"

    audit_rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.org_id == org_id, AuditLog.resource_id == family_id)
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    assert [row.action for row in audit_rows] == ["reel_family.created"]
    assert all(row.resource_type == "reel_family" for row in audit_rows)
    assert all(row.actor_id == "operator:test-user" for row in audit_rows)


def test_reel_family_create_rejects_unknown_mode(
    reel_families_client: TestClient,
    seeded_pages: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_pages["org_id"]
    page_id = seeded_pages["page_id"]

    response = reel_families_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reel-families",
        json={
            "name": "Bad mode example",
            "mode": "wildcard",
            "metadata": {},
        },
    )

    assert response.status_code == 422
    assert any(error["loc"][-1] == "mode" for error in response.json()["detail"])


def test_reel_family_routes_enforce_org_and_page_scoping(
    reel_families_client: TestClient,
    seeded_pages: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_pages["org_id"]
    other_org_id = seeded_pages["other_org_id"]
    page_id = seeded_pages["page_id"]
    other_page_id = seeded_pages["other_page_id"]

    create_response = reel_families_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reel-families",
        json={
            "name": "Scoped family",
            "mode": "exploit",
            "metadata": {"hypothesis": "Double down on the best-performing angle."},
        },
    )

    assert create_response.status_code == 201
    family_id = create_response.json()["id"]

    wrong_org_create = reel_families_client.post(
        f"/orgs/{other_org_id}/pages/{page_id}/reel-families",
        json={
            "name": "Wrong org",
            "mode": "chaos",
            "metadata": {},
        },
    )
    wrong_page_get = reel_families_client.get(
        f"/orgs/{org_id}/pages/{other_page_id}/reel-families/{family_id}"
    )

    assert wrong_org_create.status_code == 404
    assert wrong_org_create.json()["detail"] == "Page not found"
    assert wrong_page_get.status_code == 404
    assert wrong_page_get.json()["detail"] == "Reel family not found"
