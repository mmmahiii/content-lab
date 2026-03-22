from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import AuditLog, Org


@pytest.fixture
def pages_client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_orgs(db_session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    org_one = Org(name="Primary Org", slug=f"primary-{uuid.uuid4().hex[:8]}")
    org_two = Org(name="Secondary Org", slug=f"secondary-{uuid.uuid4().hex[:8]}")
    db_session.add_all([org_one, org_two])
    db_session.flush()
    return org_one.id, org_two.id


def test_pages_crud_is_org_scoped_and_audited(
    pages_client: TestClient,
    db_session: Session,
    seeded_orgs: tuple[uuid.UUID, uuid.UUID],
) -> None:
    org_id, other_org_id = seeded_orgs
    create_payload = {
        "platform": "instagram",
        "display_name": "Owned Page",
        "external_page_id": "ig-owned-001",
        "handle": "@owned.page",
        "ownership": "owned",
        "metadata": {
            "persona": {
                "label": "Calm educator",
                "audience": "Busy founders",
                "brand_tone": ["clear", "grounded"],
                "content_pillars": ["operations", "positioning"],
                "differentiators": ["operator-led advice"],
                "primary_call_to_action": "Book a strategy call",
            },
            "constraints": {
                "blocked_phrases": ["guaranteed results"],
                "required_disclosures": ["Results vary"],
                "allow_direct_cta": True,
                "max_script_words": 180,
            },
            "niche": "b2b services",
        },
    }

    create_response = pages_client.post(
        f"/orgs/{org_id}/pages",
        json=create_payload,
        headers={"X-Actor-Id": "operator:test-user"},
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["org_id"] == str(org_id)
    assert created["ownership"] == "owned"
    assert created["metadata"]["persona"]["content_pillars"] == ["operations", "positioning"]
    assert created["metadata"]["constraints"]["required_disclosures"] == ["Results vary"]
    assert created["metadata"]["niche"] == "b2b services"

    page_id = created["id"]

    list_response = pages_client.get(f"/orgs/{org_id}/pages")
    assert list_response.status_code == 200
    listed = list_response.json()
    assert [page["id"] for page in listed] == [page_id]

    get_response = pages_client.get(f"/orgs/{org_id}/pages/{page_id}")
    assert get_response.status_code == 200
    assert get_response.json()["handle"] == "@owned.page"

    cross_org_response = pages_client.get(f"/orgs/{other_org_id}/pages/{page_id}")
    assert cross_org_response.status_code == 404
    assert cross_org_response.json()["detail"] == "Page not found"

    update_response = pages_client.patch(
        f"/orgs/{org_id}/pages/{page_id}",
        json={
            "display_name": "Owned Page Updated",
            "handle": "@owned.updated",
            "metadata": {
                "persona": {
                    "label": "Direct operator",
                    "audience": "Early-stage teams",
                    "brand_tone": ["practical"],
                    "content_pillars": ["systems"],
                },
                "constraints": {
                    "blocked_phrases": ["overnight success"],
                    "allow_direct_cta": False,
                },
                "market": "uk",
            },
        },
        headers={"X-Actor-Id": "operator:test-user"},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["display_name"] == "Owned Page Updated"
    assert updated["handle"] == "@owned.updated"
    assert updated["metadata"]["persona"]["label"] == "Direct operator"
    assert updated["metadata"]["constraints"]["allow_direct_cta"] is False
    assert updated["metadata"]["market"] == "uk"

    audit_rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.org_id == org_id, AuditLog.resource_id == page_id)
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    assert [row.action for row in audit_rows] == ["page.created", "page.updated"]
    assert all(row.resource_type == "page" for row in audit_rows)
    assert all(row.actor_id == "operator:test-user" for row in audit_rows)


def test_pages_can_be_filtered_by_ownership(
    pages_client: TestClient,
    seeded_orgs: tuple[uuid.UUID, uuid.UUID],
) -> None:
    org_id, _ = seeded_orgs
    owned_payload = {
        "platform": "instagram",
        "display_name": "Owned",
        "external_page_id": "page-owned-001",
        "ownership": "owned",
        "metadata": {"constraints": {}},
    }
    competitor_payload = {
        "platform": "instagram",
        "display_name": "Competitor",
        "external_page_id": "page-competitor-001",
        "ownership": "competitor",
        "metadata": {"constraints": {"blocked_phrases": ["our product"]}},
    }

    owned_response = pages_client.post(f"/orgs/{org_id}/pages", json=owned_payload)
    competitor_response = pages_client.post(f"/orgs/{org_id}/pages", json=competitor_payload)

    assert owned_response.status_code == 201
    assert competitor_response.status_code == 201

    all_response = pages_client.get(f"/orgs/{org_id}/pages")
    owned_only_response = pages_client.get(f"/orgs/{org_id}/pages?ownership=owned")
    competitor_only_response = pages_client.get(f"/orgs/{org_id}/pages?ownership=competitor")

    assert all_response.status_code == 200
    assert owned_only_response.status_code == 200
    assert competitor_only_response.status_code == 200
    assert {page["ownership"] for page in all_response.json()} == {"owned", "competitor"}
    assert [page["ownership"] for page in owned_only_response.json()] == ["owned"]
    assert [page["ownership"] for page in competitor_only_response.json()] == ["competitor"]
