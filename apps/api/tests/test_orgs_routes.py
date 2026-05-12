from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import Org, Page


def test_list_orgs_returns_every_existing_org_with_page_counts(
    db_session: Session,
) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    try:
        org_with_pages = Org(name="Food Assets Org", slug="food-assets-org")
        empty_org = Org(name="Runway Test Org", slug="runway-test-org")
        db_session.add_all([org_with_pages, empty_org])
        db_session.flush()
        db_session.add(
            Page(
                org_id=org_with_pages.id,
                platform="instagram",
                display_name="Food PNG Assets",
                external_page_id="food-png-assets",
                handle="@food.png.assets",
                kind="owned",
                metadata_={},
            )
        )
        db_session.flush()

        response = client.get("/orgs")

        assert response.status_code == 200
        orgs = response.json()
        org_by_slug = {org["slug"]: org for org in orgs}
        assert org_by_slug["food-assets-org"]["page_count"] == 1
        assert org_by_slug["runway-test-org"]["page_count"] == 0
    finally:
        app.dependency_overrides.clear()
