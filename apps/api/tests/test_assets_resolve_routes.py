from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import Asset, AssetGenParam, Org, Task
from content_lab_assets.registry import build_asset_key


@pytest.fixture
def assets_client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def org_id(db_session: Session) -> uuid.UUID:
    org = Org(name="Asset Org", slug=f"asset-org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return org.id


def _resolve_payload(*, reference_asset_ids: list[uuid.UUID]) -> dict[str, Any]:
    return {
        "asset_class": "clip",
        "provider": "Runway",
        "model": "GEN4.5",
        "prompt": "  Hero   launch  shot ",
        "negative_prompt": "  no text overlays ",
        "seed": 7,
        "duration_seconds": 6.0,
        "fps": 24,
        "ratio": " 9:16 ",
        "motion": {
            "camera": {"pan": " slow left "},
            "strength": 0.6,
        },
        "init_image_hash": " ABC123 ",
        "reference_asset_ids": [
            str(reference_asset_id) for reference_asset_id in reference_asset_ids
        ],
        "metadata": {"shot_id": "hero-1"},
    }


def test_asset_resolve_reuses_exact_match_deterministically(
    assets_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    reference_one = uuid.uuid4()
    reference_two = uuid.uuid4()
    payload = _resolve_payload(reference_asset_ids=[reference_two, reference_one])
    asset_key = build_asset_key(
        asset_class=str(payload["asset_class"]),
        provider=str(payload["provider"]),
        model=str(payload["model"]),
        prompt=str(payload["prompt"]),
        negative_prompt=str(payload["negative_prompt"]),
        seed=int(payload["seed"]),
        duration_seconds=float(payload["duration_seconds"]),
        fps=int(payload["fps"]),
        ratio=str(payload["ratio"]),
        motion=payload["motion"],
        init_image_hash=str(payload["init_image_hash"]),
        reference_asset_ids=[reference_two, reference_one],
    )

    asset_id = uuid.uuid4()
    db_session.execute(
        insert(Asset).values(
            id=asset_id,
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://content-lab/assets/existing.mp4",
            status="ready",
            asset_key=asset_key.asset_key,
            asset_key_hash=asset_key.asset_key_hash,
            metadata_={"source": "seed"},
        )
    )
    db_session.execute(
        insert(AssetGenParam).values(
            id=uuid.uuid4(),
            org_id=org_id,
            asset_id=asset_id,
            seq=0,
            asset_key_hash=asset_key.asset_key_hash,
            canonical_params=asset_key.canonical_params,
        )
    )
    db_session.flush()

    first_response = assets_client.post(f"/orgs/{org_id}/assets/resolve", json=payload)
    assert first_response.status_code == 200
    first_decision = first_response.json()
    assert first_decision["decision"] == "reuse_exact"
    assert first_decision["asset_id"] == str(asset_id)
    assert first_decision["asset_key_hash"] == asset_key.asset_key_hash
    assert first_decision["canonical_params"]["provider"] == "runway"
    assert first_decision["canonical_params"]["model"] == "gen4.5"
    assert first_decision["canonical_params"]["prompt"] == "Hero launch shot"
    assert first_decision["canonical_params"]["reference_asset_ids"] == sorted(
        [str(reference_one), str(reference_two)]
    )

    second_payload = _resolve_payload(reference_asset_ids=[reference_one, reference_two])
    second_payload["provider"] = "runway"
    second_payload["model"] = "gen4.5"
    second_payload["prompt"] = "Hero launch shot"
    second_payload["negative_prompt"] = "no text overlays"
    second_payload["ratio"] = "9:16"
    second_payload["init_image_hash"] = "abc123"
    second_response = assets_client.post(f"/orgs/{org_id}/assets/resolve", json=second_payload)

    assert second_response.status_code == 200
    second_decision = second_response.json()
    assert second_decision["decision"] == "reuse_exact"
    assert second_decision["asset_id"] == first_decision["asset_id"]
    assert second_decision["asset_key"] == first_decision["asset_key"]
    assert second_decision["asset_key_hash"] == first_decision["asset_key_hash"]
    assert db_session.query(Task).filter(Task.org_id == org_id).count() == 0


def test_asset_resolve_generate_path_reuses_generation_intent(
    assets_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    payload = _resolve_payload(reference_asset_ids=[uuid.uuid4()])

    first_response = assets_client.post(f"/orgs/{org_id}/assets/resolve", json=payload)
    assert first_response.status_code == 200
    first_decision = first_response.json()
    assert first_decision["decision"] == "generate"
    asset_id = first_decision["generation_intent"]["asset_id"]
    task_id = first_decision["generation_intent"]["task_id"]
    assert first_decision["generation_intent"]["asset_status"] == "staged"
    assert first_decision["generation_intent"]["storage_uri"].startswith(
        "s3://content-lab/assets/raw/"
    )
    assert first_decision["generation_intent"]["task_type"] == "asset.generate"
    assert first_decision["generation_intent"]["payload"]["provenance"]["source"] == (
        "asset_registry.resolve"
    )

    second_payload = dict(payload)
    second_payload["provider"] = " runway "
    second_payload["model"] = " gen4.5 "
    second_payload["prompt"] = "Hero launch shot"
    second_response = assets_client.post(f"/orgs/{org_id}/assets/resolve", json=second_payload)

    assert second_response.status_code == 200
    second_decision = second_response.json()
    assert second_decision["decision"] == "generate"
    assert second_decision["generation_intent"]["asset_id"] == asset_id
    assert second_decision["generation_intent"]["task_id"] == task_id
    assert second_decision["asset_key_hash"] == first_decision["asset_key_hash"]

    assets = db_session.query(Asset).filter(Asset.org_id == org_id).all()
    assert len(assets) == 1
    assert str(assets[0].id) == asset_id
    assert assets[0].status == "staged"
    assert assets[0].asset_key_hash == first_decision["asset_key_hash"]
    params = db_session.query(AssetGenParam).filter(AssetGenParam.asset_id == assets[0].id).all()
    assert len(params) == 1
    assert params[0].seq == 0
    tasks = db_session.query(Task).filter(Task.org_id == org_id).all()
    assert len(tasks) == 1
    assert tasks[0].idempotency_key == f"asset.generate:{first_decision['asset_key_hash']}"
    assert tasks[0].payload["canonical_params"]["provider"] == "runway"
    assert tasks[0].payload["canonical_params"]["model"] == "gen4.5"


def test_asset_resolve_switches_from_staged_generate_to_ready_reuse(
    assets_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    payload = _resolve_payload(reference_asset_ids=[uuid.uuid4()])

    first_response = assets_client.post(f"/orgs/{org_id}/assets/resolve", json=payload)
    assert first_response.status_code == 200
    first_decision = first_response.json()
    assert first_decision["decision"] == "generate"
    asset_id = uuid.UUID(first_decision["generation_intent"]["asset_id"])

    asset = db_session.get(Asset, asset_id)
    assert asset is not None
    asset.status = "ready"
    asset.storage_uri = "s3://content-lab/assets/derived/generated.mp4"
    db_session.flush()

    second_response = assets_client.post(f"/orgs/{org_id}/assets/resolve", json=payload)
    assert second_response.status_code == 200
    second_decision = second_response.json()
    assert second_decision["decision"] == "reuse_exact"
    assert second_decision["asset_id"] == str(asset_id)
    assert second_decision["storage_uri"] == "s3://content-lab/assets/derived/generated.mp4"
    assert db_session.query(Asset).filter(Asset.org_id == org_id).count() == 1


def test_asset_detail_returns_org_scoped_metadata_and_signed_download(
    assets_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    asset = Asset(
        org_id=org_id,
        asset_class="clip",
        storage_uri="s3://content-lab/assets/derived/clip-123.mp4",
        source="runway",
        asset_key="asset-key-123",
        asset_key_hash="asset-hash-123",
        content_hash="sha256:abc123",
        metadata_={"duration_seconds": 6},
    )
    db_session.add(asset)
    db_session.flush()

    db_session.add(
        AssetGenParam(
            org_id=org_id,
            asset_id=asset.id,
            seq=0,
            asset_key_hash="asset-hash-123",
            canonical_params={"provider": "runway", "model": "gen4.5"},
        )
    )
    db_session.flush()

    response = assets_client.get(f"/orgs/{org_id}/assets/{asset.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(asset.id)
    assert payload["org_id"] == str(org_id)
    assert payload["storage_uri"] == "s3://content-lab/assets/derived/clip-123.mp4"
    assert payload["canonical_params"] == {"provider": "runway", "model": "gen4.5"}
    assert payload["provenance"]["asset_key_hash"] == "asset-hash-123"
    assert payload["download"]["storage_uri"] == payload["storage_uri"]
    assert payload["download"]["url"].startswith(
        "http://localhost:9000/content-lab/assets/derived/clip-123.mp4?"
    )


def test_asset_download_is_org_scoped(
    assets_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    other_org = Org(name="Other Asset Org", slug=f"other-asset-org-{uuid.uuid4().hex[:8]}")
    db_session.add(other_org)
    db_session.flush()

    other_asset = Asset(
        org_id=other_org.id,
        asset_class="image",
        storage_uri="s3://content-lab/assets/other.png",
    )
    db_session.add(other_asset)
    db_session.flush()

    response = assets_client.get(f"/orgs/{org_id}/assets/{other_asset.id}/download")

    assert response.status_code == 404
    assert response.json()["detail"] == "Asset not found"


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("pika", "gen4.5"),
        ("runway", "gen4"),
    ],
)
def test_asset_resolve_rejects_non_phase1_provider_model(
    assets_client: TestClient,
    org_id: uuid.UUID,
    provider: str,
    model: str,
) -> None:
    payload = _resolve_payload(reference_asset_ids=[])
    payload["provider"] = provider
    payload["model"] = model

    response = assets_client.post(f"/orgs/{org_id}/assets/resolve", json=payload)

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "phase-1 asset resolution only supports provider='runway' and model='gen4.5'"
    )
