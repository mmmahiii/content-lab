from __future__ import annotations

import base64
import uuid
from collections import Counter
from collections.abc import Generator
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import (
    Asset,
    AssetGenParam,
    AssetPack,
    AssetPackItem,
    AuditLog,
    Org,
    OutboxEvent,
    Page,
    PlannedAssetSpec,
    Reel,
    ReelFamily,
    Run,
    Task,
)
from content_lab_api.schemas.asset_packs import SourceAssetRegisterRequest
from content_lab_api.services.asset_packs import detach_asset_from_pack, register_source_asset_for_pack
from content_lab_assets.registry import validate_asset_kind_media_type
from content_lab_shared.settings import Settings
from content_lab_storage import StorageRef, StoredObject

_PNG_1X1_TRANSPARENT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mP8z8AARQAFAAIB"
    "AaxooGQAAAAASUVORK5CYII="
)


class _FakeStorageClient:
    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []

    def put_object(
        self,
        *,
        data: bytes,
        ref: StorageRef | None = None,
        storage_uri: str | None = None,
        key: str | None = None,
        bucket: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        checksum_sha256: str | None = None,
    ) -> StoredObject:
        assert ref is not None
        self.puts.append(
            {
                "data": data,
                "ref": ref,
                "content_type": content_type,
                "metadata": metadata or {},
                "checksum_sha256": checksum_sha256,
            }
        )
        return StoredObject(
            ref=ref,
            size_bytes=len(data),
            content_type=content_type,
            metadata=metadata or {},
            checksum_sha256=checksum_sha256,
        )


@pytest.fixture
def asset_pack_client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def org_id(db_session: Session) -> uuid.UUID:
    org = Org(name="Asset Pack Org", slug=f"asset-pack-org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return cast(uuid.UUID, org.id)


def test_asset_pack_plan_route_persists_pack_specs_and_items(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Pilates reusable kit",
            "niche": "pilates",
            "target_audience": "desk workers rebuilding strength",
            "requested_asset_count": 4,
            "target_reel_types": ["form tip", "before-after"],
            "style_persona_constraints": {
                "tone": "calm educator",
                "core_motifs": ["mat setup", "slow form correction"],
            },
        },
        headers={"X-Actor-Id": "operator:planner"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["asset_pack"]["status"] == "planned"
    assert payload["asset_pack"]["requested_asset_count"] == 4
    assert sum(payload["asset_mix"].values()) == 4
    assert len(payload["planned_asset_specs"]) == 4
    assert payload["expected_reel_formats"] == ["form tip", "before-after"]
    assert payload["reuse_rationale"]
    assert payload["asset_pack"]["target_audience"] == "desk workers rebuilding strength"
    assert payload["asset_pack_plan"]["pack_strategy"]["target_audience"] == (
        "desk workers rebuilding strength"
    )
    assert payload["asset_pack_plan"]["pack_strategy"]["core_motifs"] == [
        "mat setup",
        "slow form correction",
    ]
    assert "desk workers rebuilding strength" in payload["strategy_summary"]
    assert payload["asset_pack_plan"]["output_potential_scoring"]["top_priority_assets"]
    assert all(spec["output_potential_score"] > 0 for spec in payload["planned_asset_specs"])

    pack_id = uuid.UUID(payload["asset_pack"]["id"])
    assert db_session.query(AssetPack).filter(AssetPack.id == pack_id).count() == 1
    assert (
        db_session.query(PlannedAssetSpec).filter(PlannedAssetSpec.asset_pack_id == pack_id).count()
        == 4
    )
    assert (
        db_session.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == pack_id).count() == 4
    )
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.org_id == org_id, AuditLog.resource_id == str(pack_id))
        .one()
    )
    assert audit.action == "asset_pack.plan.created"
    assert audit.actor_id == "operator:planner"
    assert audit.payload["pack_strategy"]["target_audience"] == "desk workers rebuilding strength"
    assert "Asset pack strategy" in audit.payload["strategy_summary"]

    persisted_spec = (
        db_session.query(PlannedAssetSpec)
        .filter(PlannedAssetSpec.asset_pack_id == pack_id)
        .order_by(PlannedAssetSpec.priority)
        .first()
    )
    assert persisted_spec is not None
    assert persisted_spec.required_traits["output_potential"]["score"] > 0


def test_asset_pack_planning_smoke_honors_requested_asset_count_thirty(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Luxury mindset asset bank",
            "niche": "luxury mindset",
            "requested_asset_count": 30,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    pack_id = uuid.UUID(payload["asset_pack"]["id"])
    planned_specs = payload["planned_asset_specs"]
    asset_mix = payload["asset_mix"]

    assert payload["asset_pack"]["status"] == "planned"
    assert payload["asset_pack"]["niche"] == "luxury mindset"
    assert payload["asset_pack"]["requested_asset_count"] == 30
    assert payload["asset_pack_plan"]
    assert payload["reuse_rationale"]
    assert payload["strategy_summary"]
    assert len(planned_specs) == 30
    assert sum(asset_mix.values()) == 30
    assert all(count > 0 for count in asset_mix.values())

    planned_counts: dict[str, int] = {}
    for spec in planned_specs:
        planned_counts[spec["asset_kind"]] = planned_counts.get(spec["asset_kind"], 0) + 1
        validate_asset_kind_media_type(
            asset_kind=spec["asset_kind"],
            media_type=spec["media_type"],
        )
        assert spec["rationale"]
        assert spec["output_potential_rationale"]
        assert spec["priority"] >= 0

    assert planned_counts == asset_mix
    assert db_session.query(AssetPack).filter(AssetPack.id == pack_id).count() == 1
    assert (
        db_session.query(PlannedAssetSpec).filter(PlannedAssetSpec.asset_pack_id == pack_id).count()
        == 30
    )
    assert (
        db_session.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == pack_id).count()
        == 30
    )


def test_asset_pack_crud_routes_create_list_get_plan_and_items(
    asset_pack_client: TestClient,
    org_id: uuid.UUID,
) -> None:
    create_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs",
        json={
            "name": "Operator-defined pack",
            "niche": "coffee shop marketing",
            "requested_asset_count": 3,
            "asset_mix_requested_json": {"hook_text": 1, "prop_image": 2},
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["status"] == "draft"
    assert created["requested_asset_count"] == 3
    pack_id = uuid.UUID(created["id"])

    list_response = asset_pack_client.get(f"/orgs/{org_id}/asset-packs?status=draft")
    assert list_response.status_code == 200
    assert [row["id"] for row in list_response.json()] == [str(pack_id)]

    get_response = asset_pack_client.get(f"/orgs/{org_id}/asset-packs/{pack_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Operator-defined pack"

    plan_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack_id}/plan",
        json={
            "name": "Operator-defined pack",
            "niche": "coffee shop marketing",
            "requested_asset_count": 3,
            "asset_mix": {"hook_text": 1, "prop_image": 2},
        },
    )
    assert plan_response.status_code == 200
    planned = plan_response.json()
    assert planned["asset_pack"]["id"] == str(pack_id)
    assert planned["asset_pack"]["status"] == "planned"
    assert len(planned["planned_asset_specs"]) == 3

    items_response = asset_pack_client.get(f"/orgs/{org_id}/asset-packs/{pack_id}/items")
    assert items_response.status_code == 200
    assert len(items_response.json()) == 3


def test_asset_pack_combinations_route_returns_candidate_manifests(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    pack = AssetPack(
        org_id=org_id,
        name="Combination kit",
        niche="pilates",
        requested_asset_count=3,
        status="ready",
    )
    db_session.add(pack)
    db_session.flush()
    assets = {
        "background": Asset(
            org_id=org_id,
            asset_class="component",
            storage_uri="s3://content-lab/assets/bg.mp4",
            status="ready",
        ),
        "hook": Asset(
            org_id=org_id,
            asset_class="component",
            storage_uri="s3://content-lab/assets/hook.txt",
            status="ready",
        ),
        "audio": Asset(
            org_id=org_id,
            asset_class="component",
            storage_uri="s3://content-lab/assets/audio.mp3",
            status="ready",
        ),
    }
    db_session.add_all(assets.values())
    db_session.flush()
    for role, asset_kind in [
        ("background", "background_video"),
        ("hook", "hook_text"),
        ("audio", "audio_track"),
    ]:
        db_session.add(
            AssetPackItem(
                asset_pack_id=pack.id,
                asset_id=assets[role].id,
                asset_kind=asset_kind,
                pack_role=role,
                status="selected",
                metadata_json={"title": f"{role} asset"},
                compatibility_metadata={
                    "niche": ["pilates"],
                    "visual_style": ["clean"],
                    "format_type": ["hook-led tip"],
                },
            )
        )
    db_session.flush()

    response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack.id}/combinations",
        json={
            "target_reel_count": 2,
            "filters": {"formats": ["hook-led tip"], "styles": ["clean"]},
            "mode": "balanced",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_pack"]["id"] == str(pack.id)
    candidates = payload["candidate_compositions"]
    assert len(candidates) == 1
    assert set(candidates[0]["roles"]) == {"audio", "background", "hook"}
    assert candidates[0]["composition_manifest"]["asset_pack_id"] == str(pack.id)
    assert candidates[0]["composition_manifest"]["roles"]["hook"]["asset_id"] == str(
        assets["hook"].id
    )


def test_asset_pack_to_multiple_reels_smoke_returns_overlapping_candidates(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    pack = AssetPack(
        org_id=org_id,
        name="Reusable luxury reel kit",
        niche="luxury mindset",
        requested_asset_count=8,
        status="ready",
    )
    db_session.add(pack)
    db_session.flush()
    component_specs = [
        ("background_a", "background_image", "background", 0),
        ("background_b", "background_image", "background", 1),
        ("object_a", "transparent_cutout_png", "foreground", 2),
        ("object_b", "transparent_cutout_png", "foreground", 3),
        ("hook_a", "hook_text", "hook", 4),
        ("hook_b", "hook_text", "hook", 5),
        ("audio_a", "audio_track", "audio", 6),
        ("audio_b", "audio_track", "audio", 7),
    ]
    assets: dict[str, Asset] = {}
    for label, asset_kind, role, priority in component_specs:
        asset = Asset(
            org_id=org_id,
            asset_class="component",
            storage_uri=f"s3://content-lab/assets/{label}",
            status="ready",
        )
        db_session.add(asset)
        db_session.flush()
        assets[label] = asset
        db_session.add(
            AssetPackItem(
                asset_pack_id=pack.id,
                asset_id=asset.id,
                asset_kind=asset_kind,
                pack_role=role,
                status="selected",
                priority=priority,
                metadata_json={"title": label.replace("_", " ")},
                compatibility_metadata={
                    "niche": ["luxury_mindset"],
                    "visual_style": ["cinematic"],
                    "format_type": ["hook_led_tip"],
                    "emotion": ["aspirational"],
                },
            )
        )
    db_session.flush()

    response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack.id}/combinations",
        json={
            "target_reel_count": 5,
            "filters": {"formats": ["hook_led_tip"], "styles": ["cinematic"]},
            "mode": "balanced",
        },
    )

    assert response.status_code == 200
    candidates = response.json()["candidate_compositions"]
    assert len(candidates) == 5
    assert len({candidate["composition_id"] for candidate in candidates}) == 5
    assert all(
        set(candidate["roles"]) == {"audio", "background", "foreground", "hook"}
        for candidate in candidates
    )
    role_asset_counts = Counter(
        role_payload["asset_id"]
        for candidate in candidates
        for role_payload in candidate["roles"].values()
    )
    assert max(role_asset_counts.values()) > 1
    assert any(
        candidate["composition_manifest"]["roles"]["background"]["asset_id"]
        in {str(assets["background_a"].id), str(assets["background_b"].id)}
        for candidate in candidates
    )


def test_asset_pack_composition_render_submit_creates_local_hook_cover_output(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    page = Page(
        org_id=org_id,
        platform="instagram",
        display_name="Pilates Studio",
        handle="pilates",
    )
    pack = AssetPack(
        org_id=org_id,
        name="Renderable kit",
        niche="pilates",
        requested_asset_count=1,
        status="ready",
    )
    db_session.add_all([page, pack])
    db_session.flush()
    manifest = {
        "schema_version": "asset_composition_manifest.v1",
        "asset_pack_id": str(pack.id),
        "composition_id": "composition-1",
        "roles": {"hook": {"asset_id": str(uuid.uuid4()), "asset_kind": "hook_text"}},
    }
    response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack.id}/composition-renders",
        json={
            "page_id": str(page.id),
            "composition_manifest": manifest,
            "render_mode": "preview",
            "dry_run": True,
            "idempotency_key": f"composition-render:{pack.id}:composition-1",
            "metadata": {"operator_note": "preview this"},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    run = db_session.get(Run, uuid.UUID(payload["run_id"]))
    task = db_session.get(Task, uuid.UUID(payload["task_id"]))
    reel = db_session.get(Reel, uuid.UUID(payload["reel_id"]))
    family = db_session.get(ReelFamily, uuid.UUID(payload["reel_family_id"]))
    assert run is not None
    assert task is not None
    assert reel is not None
    assert family is not None
    assert payload["accepted_for_rendering"] is True
    assert run.workflow_key == "process_reel"
    assert run.status == "succeeded"
    assert run.external_ref is not None and run.external_ref.startswith("outbox:")
    assert run.input_params["composition_manifest"]["composition_id"] == "composition-1"
    assert task.status == "succeeded"
    assert task.payload["render_mode"] == "preview"
    assert reel.status == "ready"
    assert reel.metadata_["idea_plan"]["composition_manifest"]["composition_id"] == "composition-1"
    assert family.metadata_["composition_manifest"]["composition_id"] == "composition-1"
    assert family.metadata_["idea_plan"]["hook"] == "hook_text"
    assert run.output_payload["output_type"] == "hook_cover_image"
    assert run.output_payload["package"]["hook_cover"]["hook"] == "hook_text"
    outbox = (
        db_session.query(OutboxEvent)
        .filter(OutboxEvent.aggregate_type == "run", OutboxEvent.aggregate_id == str(run.id))
        .one()
    )
    assert outbox.event_type == "orchestration.flow.requested"
    assert outbox.payload["workflow_key"] == "process_reel"
    assert db_session.query(AuditLog).filter(AuditLog.resource_id == str(run.id)).count() == 1


def test_asset_pack_plan_route_preserves_exact_operator_mix(
    asset_pack_client: TestClient,
    org_id: uuid.UUID,
) -> None:
    response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Coffee kit",
            "niche": "coffee shop marketing",
            "requested_asset_count": 4,
            "asset_mix": {
                "backgrounds": 1,
                "detail_prop": 2,
                "hook_text": 1,
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["asset_mix"] == {
        "background_video": 1,
        "prop_image": 2,
        "hook_text": 1,
    }
    assert payload["asset_pack"]["asset_mix_requested_json"] == {
        "background_video": 1,
        "prop_image": 2,
        "hook_text": 1,
    }
    assert len(payload["planned_asset_specs"]) == 4
    assert [spec["priority"] for spec in payload["planned_asset_specs"]] == list(range(4))
    assert payload["planned_asset_specs"][0]["output_potential_rationale"]


def test_asset_pack_plan_route_rejects_mix_total_mismatch(
    asset_pack_client: TestClient,
    org_id: uuid.UUID,
) -> None:
    response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "niche": "coffee shop marketing",
            "requested_asset_count": 5,
            "asset_mix": {
                "background_video": 2,
                "hook_text": 1,
            },
        },
    )

    assert response.status_code == 422
    assert "asset_mix total must equal requested_asset_count" in response.text


def test_asset_pack_review_gate_blocks_direct_generation_and_requires_approval(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    direct_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/generate",
        json={
            "name": "Ungated kit",
            "niche": "coffee shop marketing",
            "requested_asset_count": 1,
            "asset_mix": {"hook_text": 1},
        },
    )
    assert direct_response.status_code == 409
    assert "approve it" in direct_response.json()["detail"]

    plan_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Reviewable kit",
            "niche": "coffee shop marketing",
            "requested_asset_count": 1,
            "asset_mix": {"hook_text": 1},
        },
    )
    assert plan_response.status_code == 201
    pack_id = uuid.UUID(plan_response.json()["asset_pack"]["id"])

    unapproved_generate = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack_id}/generate",
        json={},
    )
    assert unapproved_generate.status_code == 422
    assert unapproved_generate.json()["detail"] == "Asset pack must be approved before generation"

    approve_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack_id}/approve",
        json={"note": "Ship this plan", "metadata": {"review_channel": "ops"}},
        headers={"X-Actor-Id": "operator:reviewer"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.resource_id == str(pack_id), AuditLog.action == "asset_pack.plan.approved")
        .one()
    )
    assert audit.actor_id == "operator:reviewer"
    assert audit.payload["note"] == "Ship this plan"
    assert audit.payload["metadata"] == {"review_channel": "ops"}


def test_asset_pack_reject_and_regenerate_plan_resets_review_state(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    plan_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Rejectable kit",
            "niche": "coffee shop marketing",
            "requested_asset_count": 2,
            "asset_mix": {"hook_text": 1, "prop_image": 1},
        },
    )
    assert plan_response.status_code == 201
    pack_id = uuid.UUID(plan_response.json()["asset_pack"]["id"])

    reject_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack_id}/reject",
        json={"note": "Too random"},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    regenerate_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack_id}/regenerate-plan",
        json={
            "name": "Regenerated kit",
            "niche": "coffee shop marketing",
            "requested_asset_count": 3,
            "asset_mix": {"hook_text": 1, "prop_image": 2},
            "target_reel_types": ["product tease"],
        },
    )
    assert regenerate_response.status_code == 200
    regenerated = regenerate_response.json()
    assert regenerated["asset_pack"]["status"] == "planned"
    assert regenerated["asset_pack"]["name"] == "Regenerated kit"
    assert regenerated["asset_mix"] == {"hook_text": 1, "prop_image": 2}
    assert len(regenerated["planned_asset_specs"]) == 3
    assert (
        db_session.query(PlannedAssetSpec).filter(PlannedAssetSpec.asset_pack_id == pack_id).count()
        == 3
    )
    assert (
        db_session.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == pack_id).count() == 3
    )
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == str(pack_id),
            AuditLog.action == "asset_pack.plan.regenerated",
        )
        .one()
    )
    assert audit.payload["requested_asset_count"] == 3


def test_asset_resolve_rejects_asset_pack_generation_without_planned_spec(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    pack = AssetPack(
        org_id=org_id,
        name="Unplanned generation guard",
        niche="fitness",
        requested_asset_count=2,
        status="planned",
    )
    db_session.add(pack)
    db_session.flush()

    response = asset_pack_client.post(
        f"/orgs/{org_id}/assets/resolve",
        json={
            "asset_class": "clip",
            "provider": "runway",
            "model": "gen4.5",
            "prompt": "Fitness opener",
            "metadata": {"asset_pack_id": str(pack.id)},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Asset pack generation requires metadata.planned_asset_spec_id"
    )


def test_asset_pack_generate_reuses_compatible_assets_and_generates_missing(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    existing = Asset(
        org_id=org_id,
        asset_class="component",
        storage_uri="s3://content-lab/assets/library/luxury-bg.mp4",
        source="uploaded",
        status="ready",
        metadata_={
            "asset_kind": "background_video",
            "media_type": "video",
            "asset_source": "uploaded",
            "niche": "luxury mindset",
            "pack_role": "scene_setter",
            "intended_reel_formats": ["belief shift"],
        },
    )
    db_session.add(existing)
    db_session.flush()

    plan_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Luxury mindset starter",
            "niche": "luxury mindset",
            "requested_asset_count": 2,
            "asset_mix": {"background_video": 1, "hook_text": 1},
            "target_reel_types": ["belief shift"],
        },
    )
    assert plan_response.status_code == 201
    pack_id = uuid.UUID(plan_response.json()["asset_pack"]["id"])
    approve_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack_id}/approve",
        json={"note": "Looks intentional"},
        headers={"X-Actor-Id": "operator:reviewer"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack_id}/generate",
        json={},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["asset_pack"]["status"] == "generating"
    assert payload["resolution_summary"]["uploaded"] == 1
    assert payload["resolution_summary"]["generating"] == 1
    assert payload["resolution_summary"]["ready_assets"] == 1
    assert len(payload["generation_decisions"]) == 1
    assert payload["generation_decisions"][0]["decision"] == "generate"

    items = (
        db_session.query(AssetPackItem)
        .filter(AssetPackItem.asset_pack_id == pack_id)
        .order_by(AssetPackItem.priority)
        .all()
    )
    assert {item.status for item in items} == {"uploaded", "generating"}
    uploaded_item = next(item for item in items if item.status == "uploaded")
    assert uploaded_item.asset_id == existing.id
    assert uploaded_item.metadata_json["asset_selection"]["mode"] == "compatible_existing"
    assert db_session.query(Task).filter(Task.org_id == org_id).count() == 1
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.resource_id == str(pack_id), AuditLog.action == "asset_pack.plan.approved")
        .one()
    )
    assert audit.actor_id == "operator:reviewer"


def test_asset_pack_generate_marks_pack_ready_when_enough_existing_assets_are_available(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    for kind, media_type, source, role in [
        ("background_video", "video", "uploaded", "scene_setter"),
        ("hook_text", "text", "imported", "hook_copy"),
    ]:
        db_session.add(
            Asset(
                org_id=org_id,
                asset_class="component",
                storage_uri=f"s3://content-lab/assets/library/{kind}",
                source=source,
                status="ready",
                metadata_={
                    "asset_kind": kind,
                    "media_type": media_type,
                    "asset_source": source,
                    "niche": "luxury mindset",
                    "pack_role": role,
                    "intended_reel_formats": ["belief shift"],
                },
            )
        )
    db_session.flush()

    plan_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Ready from library",
            "niche": "luxury mindset",
            "requested_asset_count": 2,
            "asset_mix": {"background_video": 1, "hook_text": 1},
            "target_reel_types": ["belief shift"],
        },
    )
    assert plan_response.status_code == 201
    pack_id = uuid.UUID(plan_response.json()["asset_pack"]["id"])
    approve_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack_id}/approve",
        json={},
    )
    assert approve_response.status_code == 200

    response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/{pack_id}/generate",
        json={},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["asset_pack"]["status"] == "ready"
    assert payload["resolution_summary"]["uploaded"] == 1
    assert payload["resolution_summary"]["imported"] == 1
    assert payload["resolution_summary"]["ready_assets"] == 2
    assert payload["generation_decisions"] == []


def test_register_source_asset_for_pack_stores_png_and_attaches_item(
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    pack = AssetPack(
        org_id=org_id,
        name="Manual source kit",
        niche="coffee",
        requested_asset_count=1,
        status="planned",
    )
    db_session.add(pack)
    db_session.flush()
    storage = _FakeStorageClient()
    request = cast(Request, SimpleNamespace(state=SimpleNamespace(actor="operator:uploader")))

    asset, item, reused = register_source_asset_for_pack(
        db_session,
        request,
        org_id=org_id,
        asset_pack_id=pack.id,
        body=SourceAssetRegisterRequest(
            asset_class="component",
            asset_kind="object_image",
            asset_source="uploaded",
            pack_role="product_prop",
            filename="product.png",
            content_type="image/png",
            data_base64=base64.b64encode(_PNG_1X1_TRANSPARENT).decode("ascii"),
            metadata={"niche": "coffee"},
        ),
        storage_client=storage,
        settings=Settings(minio_bucket="content-lab"),
    )

    assert reused is False
    assert asset.status == "ready"
    assert asset.source == "uploaded"
    assert asset.content_hash is not None
    assert asset.asset_key_hash is not None
    assert asset.storage_uri == f"s3://content-lab/assets/raw/{asset.id}/product.png"
    assert asset.metadata_["asset_kind"] == "object_image"
    assert asset.metadata_["media_type"] == "image"
    assert asset.metadata_["width"] == 1
    assert asset.metadata_["height"] == 1
    assert asset.metadata_["transparency"]["has_transparency"] is True
    assert item.asset_id == asset.id
    assert item.status == "uploaded"
    assert item.pack_role == "product_prop"
    assert (
        db_session.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == pack.id).count() == 1
    )
    assert storage.puts[0]["ref"] == StorageRef(
        bucket="content-lab",
        key=f"assets/raw/{asset.id}/product.png",
    )

    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == str(pack.id),
            AuditLog.action == "asset_pack.source_asset.registered",
        )
        .one()
    )
    assert audit.actor_id == "operator:uploader"
    assert audit.payload["asset_id"] == str(asset.id)


def test_detach_asset_from_pack_removes_membership(
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    pack = AssetPack(
        org_id=org_id,
        name="Detach kit",
        niche="tea",
        requested_asset_count=1,
        status="planned",
    )
    db_session.add(pack)
    db_session.flush()
    storage = _FakeStorageClient()
    register_request = cast(Request, SimpleNamespace(state=SimpleNamespace(actor="operator:uploader")))

    asset, _, reused = register_source_asset_for_pack(
        db_session,
        register_request,
        org_id=org_id,
        asset_pack_id=pack.id,
        body=SourceAssetRegisterRequest(
            asset_class="component",
            asset_kind="object_image",
            asset_source="uploaded",
            pack_role="manual_cutout",
            filename="cutout.png",
            content_type="image/png",
            data_base64=base64.b64encode(_PNG_1X1_TRANSPARENT).decode("ascii"),
            metadata={"niche": "tea"},
        ),
        storage_client=storage,
        settings=Settings(minio_bucket="content-lab"),
    )
    assert reused is False
    assert (
        db_session.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == pack.id).count() == 1
    )

    detach_request = cast(Request, SimpleNamespace(state=SimpleNamespace(actor="operator:detach")))
    detach_asset_from_pack(
        db_session,
        detach_request,
        org_id=org_id,
        asset_pack_id=pack.id,
        asset_id=asset.id,
    )
    assert (
        db_session.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == pack.id).count() == 0
    )
    detached_audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == str(pack.id),
            AuditLog.action == "asset_pack.asset.detached",
        )
        .one()
    )
    assert detached_audit.payload["asset_id"] == str(asset.id)


def test_asset_pack_registration_smoke_moves_pack_ready_with_linked_assets(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Registered source kit",
            "niche": "luxury mindset",
            "requested_asset_count": 2,
            "asset_mix": {"object_image": 1, "hook_text": 1},
        },
    )
    assert response.status_code == 201
    pack_id = uuid.UUID(response.json()["asset_pack"]["id"])
    pack = db_session.get(AssetPack, pack_id)
    assert pack is not None
    pack.status = "generating"
    db_session.flush()
    specs = (
        db_session.query(PlannedAssetSpec)
        .filter(PlannedAssetSpec.asset_pack_id == pack_id)
        .order_by(PlannedAssetSpec.priority)
        .all()
    )
    specs_by_kind = {spec.asset_kind: spec for spec in specs}
    assert set(specs_by_kind) == {"hook_text", "object_image"}

    request = cast(Request, SimpleNamespace(state=SimpleNamespace(actor="operator:uploader")))
    storage = _FakeStorageClient()
    image_asset, image_item, image_reused = register_source_asset_for_pack(
        db_session,
        request,
        org_id=org_id,
        asset_pack_id=pack_id,
        body=SourceAssetRegisterRequest(
            asset_class="component",
            asset_kind="object_image",
            asset_source="uploaded",
            pack_role="product_prop",
            priority=0,
            planned_asset_spec_id=specs_by_kind["object_image"].id,
            filename="product.png",
            content_type="image/png",
            data_base64=base64.b64encode(_PNG_1X1_TRANSPARENT).decode("ascii"),
            metadata={"niche": "luxury mindset"},
        ),
        storage_client=storage,
        settings=Settings(minio_bucket="content-lab"),
    )
    text_asset, text_item, text_reused = register_source_asset_for_pack(
        db_session,
        request,
        org_id=org_id,
        asset_pack_id=pack_id,
        body=SourceAssetRegisterRequest(
            asset_class="component",
            asset_kind="hook_text",
            asset_source="uploaded",
            pack_role="hook_copy",
            priority=1,
            planned_asset_spec_id=specs_by_kind["hook_text"].id,
            filename="hook.txt",
            content_type="text/plain",
            data_base64=base64.b64encode(
                b"Luxury is a decision before it is a result."
            ).decode("ascii"),
            metadata={"niche": "luxury mindset"},
        ),
        storage_client=storage,
        settings=Settings(minio_bucket="content-lab"),
    )

    db_session.expire_all()
    pack = db_session.get(AssetPack, pack_id)
    assert pack is not None
    assert pack.status == "ready"
    assert image_reused is False
    assert text_reused is False
    assert {image_asset.status, text_asset.status} == {"ready"}
    assert image_asset.storage_uri.startswith(f"s3://content-lab/assets/raw/{image_asset.id}/")
    assert text_asset.storage_uri.startswith(f"s3://content-lab/assets/raw/{text_asset.id}/")
    assert image_item.asset_id == image_asset.id
    assert text_item.asset_id == text_asset.id

    items = (
        db_session.query(AssetPackItem)
        .filter(AssetPackItem.asset_pack_id == pack_id)
        .order_by(AssetPackItem.priority)
        .all()
    )
    assert len(items) == 2
    assert {item.asset_id for item in items} == {image_asset.id, text_asset.id}
    assert all(item.asset_id is not None for item in items)
    assert db_session.query(Asset).filter(Asset.org_id == org_id).count() == 2
    assert len(storage.puts) == 2
    assert all(isinstance(put["ref"], StorageRef) for put in storage.puts)
    assert all(str(cast(StorageRef, put["ref"]).uri).startswith("s3://") for put in storage.puts)


def test_component_asset_registration_regression_not_full_video_only(
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    pack = AssetPack(
        org_id=org_id,
        name="Component-first source kit",
        niche="luxury mindset",
        requested_asset_count=5,
        status="generating",
    )
    db_session.add(pack)
    db_session.flush()
    request = cast(Request, SimpleNamespace(state=SimpleNamespace(actor="operator:uploader")))
    storage = _FakeStorageClient()
    source_assets = [
        (
            "object_image",
            "hero_object",
            "object.png",
            "image/png",
            _PNG_1X1_TRANSPARENT,
        ),
        (
            "transparent_cutout_png",
            "transparent_object",
            "cutout.png",
            "image/png",
            _PNG_1X1_TRANSPARENT,
        ),
        (
            "background_image",
            "background",
            "background.png",
            "image/png",
            _PNG_1X1_TRANSPARENT,
        ),
        (
            "hook_text",
            "hook",
            "hook.txt",
            "text/plain",
            b"Luxury starts before anyone can see it.",
        ),
        (
            "audio_track",
            "audio",
            "audio.wav",
            "audio/wav",
            b"RIFF\x24\x00\x00\x00WAVEfmt ",
        ),
    ]

    registered: list[tuple[Asset, AssetPackItem]] = []
    for priority, (asset_kind, pack_role, filename, content_type, data) in enumerate(source_assets):
        asset, item, reused = register_source_asset_for_pack(
            db_session,
            request,
            org_id=org_id,
            asset_pack_id=pack.id,
            body=SourceAssetRegisterRequest(
                asset_class="component",
                asset_kind=asset_kind,
                asset_source="uploaded",
                pack_role=pack_role,
                priority=priority,
                filename=filename,
                content_type=content_type,
                data_base64=base64.b64encode(data).decode("ascii"),
                metadata={"niche": "luxury mindset"},
            ),
            storage_client=storage,
            settings=Settings(minio_bucket="content-lab"),
        )
        assert reused is False
        registered.append((asset, item))

    db_session.expire_all()
    pack = db_session.get(AssetPack, pack.id)
    assert pack is not None
    assert pack.status == "ready"
    assert db_session.query(Asset).filter(Asset.org_id == org_id).count() == 5
    assert len(storage.puts) == 5
    assert {asset.metadata_["asset_kind"] for asset, _ in registered} == {
        "audio_track",
        "background_image",
        "hook_text",
        "object_image",
        "transparent_cutout_png",
    }
    assert all(asset.asset_class == "component" for asset, _ in registered)
    assert all(asset.storage_uri.startswith(f"s3://content-lab/assets/raw/{asset.id}/") for asset, _ in registered)
    assert all(item.asset_id == asset.id for asset, item in registered)
    assert all(item.status == "uploaded" for _, item in registered)
    assert "final_render" not in {asset.metadata_["asset_kind"] for asset, _ in registered}
    assert "generated_clip" not in {asset.metadata_["asset_kind"] for asset, _ in registered}


def test_register_source_asset_for_pack_reuses_existing_source_asset_by_key(
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    pack = AssetPack(
        org_id=org_id,
        name="Manual source kit",
        niche="coffee",
        requested_asset_count=2,
        status="planned",
    )
    db_session.add(pack)
    db_session.flush()
    storage = _FakeStorageClient()
    request = cast(Request, SimpleNamespace(state=SimpleNamespace(actor="operator:uploader")))
    body = SourceAssetRegisterRequest(
        asset_class="component",
        asset_kind="object_image",
        asset_source="uploaded",
        pack_role="product_prop",
        filename="product.png",
        content_type="image/png",
        data_base64=base64.b64encode(_PNG_1X1_TRANSPARENT).decode("ascii"),
    )

    first_asset, _, first_reused = register_source_asset_for_pack(
        db_session,
        request,
        org_id=org_id,
        asset_pack_id=pack.id,
        body=body,
        storage_client=storage,
        settings=Settings(minio_bucket="content-lab"),
    )
    second_asset, second_item, second_reused = register_source_asset_for_pack(
        db_session,
        request,
        org_id=org_id,
        asset_pack_id=pack.id,
        body=body.model_copy(update={"pack_role": "hero_product", "priority": 1}),
        storage_client=storage,
        settings=Settings(minio_bucket="content-lab"),
    )

    assert first_reused is False
    assert second_reused is True
    assert second_asset.id == first_asset.id
    assert second_item.asset_id == first_asset.id
    assert second_item.pack_role == "hero_product"
    assert db_session.query(Asset).filter(Asset.org_id == org_id).count() == 1
    assert len(storage.puts) == 1


def test_register_source_asset_persists_source_metadata_and_gen_param(
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    pack = AssetPack(
        org_id=org_id,
        name="Source meta kit",
        niche="coffee",
        requested_asset_count=1,
        status="planned",
    )
    db_session.add(pack)
    db_session.flush()
    storage = _FakeStorageClient()
    request = cast(Request, SimpleNamespace(state=SimpleNamespace(actor="operator:uploader")))
    body = SourceAssetRegisterRequest(
        asset_class="component",
        asset_kind="object_image",
        asset_source="uploaded",
        pack_role="product_prop",
        filename="product.png",
        content_type="image/png",
        data_base64=base64.b64encode(_PNG_1X1_TRANSPARENT).decode("ascii"),
        source_metadata={
            "source_type": "operator_uploaded",
            "usage_allowed": True,
            "commercial_use_allowed": False,
            "licence_type": "stock_single_use",
        },
    )
    asset, _, _ = register_source_asset_for_pack(
        db_session,
        request,
        org_id=org_id,
        asset_pack_id=pack.id,
        body=body,
        storage_client=storage,
        settings=Settings(minio_bucket="content-lab"),
    )
    assert asset.metadata_["source_metadata"]["source_type"] == "operator_uploaded"
    assert asset.metadata_["source_metadata"]["licence_type"] == "stock_single_use"
    row = db_session.query(AssetGenParam).filter(AssetGenParam.asset_id == asset.id).one()
    assert row.asset_key_hash == asset.asset_key_hash
    assert row.canonical_params.get("content_hash") == asset.content_hash


def test_asset_pack_generate_records_acquisition_on_compatible_reuse(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    existing = Asset(
        org_id=org_id,
        asset_class="component",
        storage_uri="s3://content-lab/assets/library/luxury-bg.mp4",
        source="uploaded",
        status="ready",
        metadata_={
            "asset_kind": "background_video",
            "media_type": "video",
            "asset_source": "uploaded",
            "niche": "luxury mindset",
            "pack_role": "scene_setter",
            "intended_reel_formats": ["belief shift"],
        },
    )
    db_session.add(existing)
    db_session.flush()

    plan_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Luxury mindset starter",
            "niche": "luxury mindset",
            "requested_asset_count": 2,
            "asset_mix": {"background_video": 1, "hook_text": 1},
            "target_reel_types": ["belief shift"],
        },
    )
    assert plan_response.status_code == 201
    pack_id = uuid.UUID(plan_response.json()["asset_pack"]["id"])
    asset_pack_client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/approve", json={})
    asset_pack_client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/generate", json={})

    uploaded_item = (
        db_session.query(AssetPackItem)
        .filter(AssetPackItem.asset_pack_id == pack_id, AssetPackItem.asset_id == existing.id)
        .one()
    )
    acq = uploaded_item.metadata_json.get("acquisition_decision") or {}
    assert acq.get("recommended_acquisition_path") == "reuse_existing_registry_asset"
    assert acq.get("resolved_acquisition_path") == "reuse_existing_registry_asset"


def test_asset_pack_generate_blocks_planned_spec_when_acquisition_forces_block(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    plan_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "Blocked kit",
            "niche": "coffee shop marketing",
            "requested_asset_count": 1,
            "asset_mix": {"hook_text": 1},
        },
    )
    assert plan_response.status_code == 201
    pack_id = uuid.UUID(plan_response.json()["asset_pack"]["id"])
    spec = (
        db_session.query(PlannedAssetSpec)
        .filter(PlannedAssetSpec.asset_pack_id == pack_id)
        .order_by(PlannedAssetSpec.priority)
        .first()
    )
    assert spec is not None
    traits = dict(spec.required_traits or {})
    traits["acquisition"] = {"force_block": True, "block_reason": "manual QA hold"}
    spec.required_traits = traits
    db_session.flush()

    asset_pack_client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/approve", json={})
    response = asset_pack_client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/generate", json={})
    assert response.status_code == 201
    item = db_session.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == pack_id).one()
    assert item.status == "failed"
    db_session.refresh(spec)
    assert spec.status == "failed"
    acq = item.metadata_json.get("acquisition_decision") or {}
    assert acq.get("recommended_acquisition_path") == "block_or_replace_asset"
    decisions = response.json()["generation_decisions"]
    assert len(decisions) == 1
    assert decisions[0]["recommended_acquisition_path"] == "block_or_replace_asset"


def test_asset_pack_generate_attaches_approved_external_asset_id(
    asset_pack_client: TestClient,
    db_session: Session,
    org_id: uuid.UUID,
) -> None:
    ext = Asset(
        org_id=org_id,
        asset_class="component",
        storage_uri="s3://content-lab/assets/library/ext-hook.txt",
        source="imported",
        status="ready",
        metadata_={
            "asset_kind": "hook_text",
            "media_type": "text",
            "asset_source": "imported",
            "niche": "tea shop",
            "pack_role": "detail_prop",
            "intended_reel_formats": [],
        },
    )
    db_session.add(ext)
    db_session.flush()

    plan_response = asset_pack_client.post(
        f"/orgs/{org_id}/asset-packs/plan",
        json={
            "name": "External hook kit",
            "niche": "coffee shop marketing",
            "requested_asset_count": 1,
            "asset_mix": {"hook_text": 1},
            "target_reel_types": ["product tease"],
        },
    )
    assert plan_response.status_code == 201
    pack_id = uuid.UUID(plan_response.json()["asset_pack"]["id"])
    spec = (
        db_session.query(PlannedAssetSpec)
        .filter(PlannedAssetSpec.asset_pack_id == pack_id)
        .order_by(PlannedAssetSpec.priority)
        .first()
    )
    assert spec is not None
    traits = dict(spec.required_traits or {})
    traits["acquisition"] = {"approved_external_asset_id": str(ext.id)}
    spec.required_traits = traits
    db_session.flush()

    asset_pack_client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/approve", json={})
    response = asset_pack_client.post(f"/orgs/{org_id}/asset-packs/{pack_id}/generate", json={})
    assert response.status_code == 201
    item = db_session.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == pack_id).one()
    assert item.asset_id == ext.id
    assert item.metadata_json.get("asset_selection", {}).get("mode") == "approved_external_attach"
    acq = item.metadata_json.get("acquisition_decision") or {}
    assert acq.get("resolved_acquisition_path") == "use_approved_external_asset"
    assert response.json()["generation_decisions"][0]["resolved_acquisition_path"] == (
        "use_approved_external_asset"
    )
    assert db_session.query(Task).filter(Task.org_id == org_id).count() == 0
