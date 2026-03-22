from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import Org
from content_lab_api.schemas.pages import PageMetadata


def _create_org(db_session: Session) -> uuid.UUID:
    org = Org(name="Validation Org", slug=f"validation-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return org.id


def test_page_metadata_schema_rejects_invalid_persona_shape() -> None:
    with pytest.raises(Exception, match="content_pillars must contain at least one item"):
        PageMetadata.model_validate(
            {
                "persona": {
                    "label": "Helpful brand",
                    "audience": "Creators",
                    "content_pillars": [],
                }
            }
        )


def test_create_page_rejects_invalid_ownership_payload(
    db_session: Session,
) -> None:
    org_id = _create_org(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.post(
            f"/orgs/{org_id}/pages",
            json={
                "platform": "instagram",
                "display_name": "Bad Ownership",
                "ownership": "partner",
                "metadata": {"constraints": {}},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "owned" in str(response.json())
    assert "competitor" in str(response.json())


def test_create_page_rejects_invalid_persona_and_constraint_payloads(
    db_session: Session,
) -> None:
    org_id = _create_org(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        persona_response = client.post(
            f"/orgs/{org_id}/pages",
            json={
                "platform": "instagram",
                "display_name": "Bad Persona",
                "ownership": "owned",
                "metadata": {
                    "persona": {
                        "label": "Helpful brand",
                        "audience": "Creators",
                        "brand_tone": ["friendly"],
                        "content_pillars": [],
                    }
                },
            },
        )
        constraint_response = client.post(
            f"/orgs/{org_id}/pages",
            json={
                "platform": "instagram",
                "display_name": "Bad Constraint",
                "ownership": "owned",
                "metadata": {
                    "constraints": {
                        "blocked_phrases": "guaranteed growth",
                    }
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert persona_response.status_code == 422
    assert "content_pillars must contain at least one item" in str(persona_response.json())
    assert constraint_response.status_code == 422
    assert "constraint list fields must be arrays of strings" in str(constraint_response.json())
