from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import AuditLog, Org, Page, PageKind
from content_lab_api.schemas.policy import PolicyStateDocument, PolicyStateUpdate


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


def _full_policy_payload() -> dict[str, object]:
    return {
        "mode_ratios": {
            "exploit": 0.25,
            "explore": 0.45,
            "mutation": 0.2,
            "chaos": 0.1,
        },
        "budget": {
            "per_run_usd_limit": 12.5,
            "daily_usd_limit": 45.0,
            "monthly_usd_limit": 900.0,
        },
        "thresholds": {
            "similarity": {
                "warn_at": 0.68,
                "block_at": 0.86,
            },
            "min_quality_score": 0.61,
        },
    }


@pytest.fixture
def policy_client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_policy_scope(db_session: Session) -> dict[str, uuid.UUID]:
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
    other_org_page = _make_page(
        org_two.id,
        platform="instagram",
        display_name="Other Org Page",
        external_page_id="ig-other-001",
    )
    db_session.add_all([primary_page, other_org_page])
    db_session.flush()

    return {
        "org_id": org_one.id,
        "other_org_id": org_two.id,
        "page_id": primary_page.id,
        "other_org_page_id": other_org_page.id,
    }


def test_policy_routes_get_and_patch_are_scoped_and_audited(
    policy_client: TestClient,
    db_session: Session,
    seeded_policy_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_policy_scope["org_id"]
    page_id = seeded_policy_scope["page_id"]
    actor_headers = {"X-Actor-Id": "operator:policy-user"}

    create_global = policy_client.patch(
        f"/orgs/{org_id}/policy/global",
        json=_full_policy_payload(),
        headers=actor_headers,
    )
    assert create_global.status_code == 200
    created_global = create_global.json()
    assert created_global["scope_type"] == "global"
    assert created_global["scope_id"] is None
    assert created_global["state"]["mode_ratios"]["explore"] == pytest.approx(0.45)
    assert created_global["state"]["thresholds"]["similarity"]["block_at"] == pytest.approx(0.86)

    update_global = policy_client.patch(
        f"/orgs/{org_id}/policy/global",
        json={
            "thresholds": {
                "similarity": {
                    "warn_at": 0.7,
                    "block_at": 0.9,
                },
                "min_quality_score": 0.64,
            }
        },
        headers=actor_headers,
    )
    assert update_global.status_code == 200
    updated_global = update_global.json()
    assert updated_global["state"]["mode_ratios"]["exploit"] == pytest.approx(0.25)
    assert updated_global["state"]["thresholds"]["similarity"]["warn_at"] == pytest.approx(0.7)
    assert updated_global["state"]["thresholds"]["min_quality_score"] == pytest.approx(0.64)

    get_global = policy_client.get(f"/orgs/{org_id}/policy/global")
    assert get_global.status_code == 200
    assert get_global.json()["id"] == created_global["id"]
    assert get_global.json()["state"]["thresholds"]["similarity"]["block_at"] == pytest.approx(0.9)

    create_page = policy_client.patch(
        f"/orgs/{org_id}/policy/page/{page_id}",
        json={
            "budget": {
                "per_run_usd_limit": 8.0,
                "daily_usd_limit": 20.0,
                "monthly_usd_limit": 400.0,
            }
        },
        headers=actor_headers,
    )
    assert create_page.status_code == 200
    created_page = create_page.json()
    assert created_page["scope_type"] == "page"
    assert created_page["scope_id"] == str(page_id)
    assert created_page["state"]["budget"]["daily_usd_limit"] == pytest.approx(20.0)
    assert (
        created_page["state"]["mode_ratios"]
        == PolicyStateDocument().model_dump(mode="json")["mode_ratios"]
    )

    get_page = policy_client.get(f"/orgs/{org_id}/policy/page/{page_id}")
    assert get_page.status_code == 200
    assert get_page.json()["id"] == created_page["id"]

    create_niche = policy_client.patch(
        f"/orgs/{org_id}/policy/niche/fitness-coaching",
        json={"mode_ratios": _full_policy_payload()["mode_ratios"]},
        headers=actor_headers,
    )
    assert create_niche.status_code == 200
    created_niche = create_niche.json()
    assert created_niche["scope_type"] == "niche"
    assert created_niche["scope_id"] == "fitness-coaching"
    assert (
        created_niche["state"]["budget"] == PolicyStateDocument().model_dump(mode="json")["budget"]
    )

    get_niche = policy_client.get(f"/orgs/{org_id}/policy/niche/fitness-coaching")
    assert get_niche.status_code == 200
    assert get_niche.json()["id"] == created_niche["id"]

    audit_rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.org_id == org_id, AuditLog.resource_type == "policy_state")
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .all()
    )
    assert [row.action for row in audit_rows].count("policy.created") == 3
    assert [row.action for row in audit_rows].count("policy.updated") == 1
    assert all(row.actor_id == "operator:policy-user" for row in audit_rows)

    global_audit_rows = [row for row in audit_rows if row.payload["policy_key"] == "global"]
    assert len(global_audit_rows) == 2

    updated_row = next(row for row in global_audit_rows if row.action == "policy.updated")
    assert updated_row.payload["updated_fields"] == ["thresholds"]
    assert updated_row.payload["before"]["thresholds"]["similarity"]["warn_at"] == pytest.approx(
        0.68
    )
    assert updated_row.payload["after"]["thresholds"]["similarity"]["warn_at"] == pytest.approx(0.7)


def test_policy_routes_enforce_scope_boundaries(
    policy_client: TestClient,
    seeded_policy_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_policy_scope["org_id"]
    other_org_id = seeded_policy_scope["other_org_id"]
    page_id = seeded_policy_scope["page_id"]

    missing_global = policy_client.get(f"/orgs/{org_id}/policy/global")
    wrong_org_page = policy_client.patch(
        f"/orgs/{other_org_id}/policy/page/{page_id}",
        json={"mode_ratios": _full_policy_payload()["mode_ratios"]},
    )

    assert missing_global.status_code == 404
    assert missing_global.json()["detail"] == "Policy not found"
    assert wrong_org_page.status_code == 404
    assert wrong_org_page.json()["detail"] == "Page not found"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "mode_ratios": {
                    "exploit": 0.6,
                    "explore": 0.3,
                    "mutation": 0.2,
                    "chaos": 0.1,
                }
            },
            "mode_ratios must sum to 1.0",
        ),
        (
            {
                "budget": {
                    "per_run_usd_limit": 50.0,
                    "daily_usd_limit": 40.0,
                    "monthly_usd_limit": 900.0,
                }
            },
            "per_run_usd_limit must not exceed daily_usd_limit",
        ),
        (
            {
                "thresholds": {
                    "similarity": {
                        "warn_at": 0.91,
                        "block_at": 0.9,
                    },
                    "min_quality_score": 0.55,
                }
            },
            "similarity.warn_at must be lower than similarity.block_at",
        ),
        (
            {
                "thresholds": {
                    "similarity": 0.85,
                    "min_quality_score": 0.55,
                }
            },
            "Input should be a valid dictionary",
        ),
    ],
)
def test_policy_validation_rejects_malformed_ratios_and_thresholds(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        PolicyStateUpdate.model_validate(payload)
