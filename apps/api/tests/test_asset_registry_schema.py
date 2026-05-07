"""Schema-level checks for asset registry tables (requires migrated PostgreSQL)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from content_lab_api.models import (
    Asset,
    AssetCombinationPerformance,
    AssetFamily,
    AssetGenParam,
    AssetPack,
    AssetPackItem,
    AssetPerformanceSummary,
    AssetUsage,
    AssetUsageSummary,
    Org,
    Page,
    PlannedAssetSpec,
    Reel,
    ReelFamily,
    ReelMetric,
    Run,
    validate_planned_asset_spec_status_transition,
)
from content_lab_api.services.asset_metrics import (
    aggregate_reel_metric_asset_performance,
    refresh_asset_usage_summaries,
)


@pytest.fixture
def org_id(db_session: Session) -> uuid.UUID:
    oid = uuid.uuid4()
    db_session.execute(
        insert(Org).values(id=oid, name="Test Org", slug=f"test-{oid.hex[:8]}"),
    )
    db_session.flush()
    return oid


def test_assets_asset_key_hash_unique_per_org(db_session: Session, org_id: uuid.UUID) -> None:
    h = "a" * 64
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/1",
            asset_key_hash=h,
        ),
    )
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(
            insert(Asset).values(
                id=uuid.uuid4(),
                org_id=org_id,
                asset_class="clip",
                storage_uri="s3://b/2",
                asset_key_hash=h,
            ),
        )


def test_assets_asset_key_can_repeat_per_org_when_hashes_differ(
    db_session: Session, org_id: uuid.UUID
) -> None:
    key = '{"asset_class":"clip","provider":"runway"}'
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/key-1",
            asset_key=key,
        ),
    )
    db_session.flush()
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/key-2",
            asset_key=key,
            asset_key_hash="f" * 64,
        ),
    )
    db_session.flush()


def test_assets_asset_key_accepts_long_serialized_payload(
    db_session: Session, org_id: uuid.UUID
) -> None:
    long_key = '{"asset_class":"clip","prompt":"' + ("very-long-prompt-" * 64) + '"}'
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/long-key",
            asset_key=long_key,
        ),
    )
    db_session.flush()


def test_assets_multiple_null_asset_key_hash_allowed(
    db_session: Session, org_id: uuid.UUID
) -> None:
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/1",
            asset_key_hash=None,
        ),
    )
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/2",
            asset_key_hash=None,
        ),
    )
    db_session.flush()


def test_same_asset_key_hash_different_orgs_allowed(db_session: Session) -> None:
    oid1 = uuid.uuid4()
    oid2 = uuid.uuid4()
    db_session.execute(
        insert(Org).values(id=oid1, name="O1", slug=f"o1-{oid1.hex[:8]}"),
    )
    db_session.execute(
        insert(Org).values(id=oid2, name="O2", slug=f"o2-{oid2.hex[:8]}"),
    )
    db_session.flush()


def test_same_asset_key_different_orgs_allowed(db_session: Session) -> None:
    oid1 = uuid.uuid4()
    oid2 = uuid.uuid4()
    db_session.execute(
        insert(Org).values(id=oid1, name="O1-key", slug=f"o1-key-{oid1.hex[:8]}"),
    )
    db_session.execute(
        insert(Org).values(id=oid2, name="O2-key", slug=f"o2-key-{oid2.hex[:8]}"),
    )
    db_session.flush()
    key = '{"asset_class":"clip","provider":"runway"}'
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=oid1,
            asset_class="clip",
            storage_uri="s3://b/key-1",
            asset_key=key,
        ),
    )
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=oid2,
            asset_class="clip",
            storage_uri="s3://b/key-2",
            asset_key=key,
        ),
    )
    db_session.flush()
    h = "b" * 64
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=oid1,
            asset_class="clip",
            storage_uri="s3://b/1",
            asset_key_hash=h,
        ),
    )
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=oid2,
            asset_class="clip",
            storage_uri="s3://b/2",
            asset_key_hash=h,
        ),
    )
    db_session.flush()


def test_asset_gen_params_ordered_history_per_asset(db_session: Session, org_id: uuid.UUID) -> None:
    aid = uuid.uuid4()
    db_session.execute(
        insert(Asset).values(
            id=aid,
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/x",
        ),
    )
    db_session.flush()
    h1 = "c" * 64
    h2 = "d" * 64
    db_session.execute(
        insert(AssetGenParam).values(
            id=uuid.uuid4(),
            org_id=org_id,
            asset_id=aid,
            seq=0,
            asset_key_hash=h1,
            canonical_params={"seed": 1},
        ),
    )
    db_session.execute(
        insert(AssetGenParam).values(
            id=uuid.uuid4(),
            org_id=org_id,
            asset_id=aid,
            seq=1,
            asset_key_hash=h2,
            canonical_params={"seed": 2},
        ),
    )
    db_session.flush()


def test_asset_gen_params_unique_asset_seq(db_session: Session, org_id: uuid.UUID) -> None:
    aid = uuid.uuid4()
    db_session.execute(
        insert(Asset).values(
            id=aid,
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/y",
        ),
    )
    db_session.flush()
    h = "e" * 64
    db_session.execute(
        insert(AssetGenParam).values(
            id=uuid.uuid4(),
            org_id=org_id,
            asset_id=aid,
            seq=0,
            asset_key_hash=h,
            canonical_params={},
        ),
    )
    with pytest.raises(IntegrityError):
        db_session.execute(
            insert(AssetGenParam).values(
                id=uuid.uuid4(),
                org_id=org_id,
                asset_id=aid,
                seq=0,
                asset_key_hash=h,
                canonical_params={},
            ),
        )


def test_asset_gen_params_cascade_when_asset_deleted(
    db_session: Session, org_id: uuid.UUID
) -> None:
    aid = uuid.uuid4()
    pid = uuid.uuid4()
    db_session.execute(
        insert(Asset).values(
            id=aid,
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/z",
        ),
    )
    db_session.execute(
        insert(AssetGenParam).values(
            id=pid,
            org_id=org_id,
            asset_id=aid,
            seq=0,
            asset_key_hash="f" * 64,
            canonical_params={},
        ),
    )
    db_session.flush()
    db_session.execute(delete(Asset).where(Asset.id == aid))
    db_session.flush()
    assert (
        db_session.scalars(select(AssetGenParam).where(AssetGenParam.id == pid)).one_or_none()
        is None
    )


def test_asset_usage_unique_reel_asset_role(db_session: Session, org_id: uuid.UUID) -> None:
    pid = uuid.uuid4()
    fid = uuid.uuid4()
    rid = uuid.uuid4()
    aid = uuid.uuid4()
    db_session.execute(
        insert(Page).values(
            id=pid,
            org_id=org_id,
            platform="instagram",
            display_name="Test page",
        ),
    )
    db_session.execute(
        insert(ReelFamily).values(
            id=fid,
            org_id=org_id,
            page_id=pid,
            name="Test family",
        ),
    )
    db_session.execute(insert(Reel).values(id=rid, org_id=org_id, reel_family_id=fid))
    db_session.execute(
        insert(Asset).values(
            id=aid,
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/u1",
        ),
    )
    db_session.flush()
    db_session.execute(
        insert(AssetUsage).values(
            id=uuid.uuid4(),
            org_id=org_id,
            reel_id=rid,
            asset_id=aid,
            usage_role="background",
            component_role="background_video",
            layer_role="base",
            sequence_index=0,
            z_index=0,
            start_time=0.0,
            end_time=2.0,
            transform_recipe={"crop": "9:16"},
            transform_version="v1",
            metadata_json={"scene_id": "scene-1"},
        ),
    )
    row = db_session.scalars(select(AssetUsage).where(AssetUsage.asset_id == aid)).one()
    assert row.component_role == "background_video"
    assert row.transform_recipe == {"crop": "9:16"}
    assert row.metadata_json == {"scene_id": "scene-1"}
    with pytest.raises(IntegrityError):
        db_session.execute(
            insert(AssetUsage).values(
                id=uuid.uuid4(),
                org_id=org_id,
                reel_id=rid,
                asset_id=aid,
                usage_role="background",
            ),
        )


def test_asset_usage_rejects_unknown_reel(db_session: Session, org_id: uuid.UUID) -> None:
    aid = uuid.uuid4()
    db_session.execute(
        insert(Asset).values(
            id=aid,
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/u2",
        ),
    )
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(
            insert(AssetUsage).values(
                id=uuid.uuid4(),
                org_id=org_id,
                reel_id=uuid.uuid4(),
                asset_id=aid,
                usage_role="voiceover",
            ),
        )


def test_asset_usage_summary_counts_reel_pack_and_component_roles(
    db_session: Session, org_id: uuid.UUID
) -> None:
    pid = uuid.uuid4()
    fid = uuid.uuid4()
    rid = uuid.uuid4()
    aid = uuid.uuid4()
    pack_id = uuid.uuid4()
    db_session.execute(
        insert(Page).values(id=pid, org_id=org_id, platform="instagram", display_name="Page")
    )
    db_session.execute(
        insert(ReelFamily).values(id=fid, org_id=org_id, page_id=pid, name="Family")
    )
    db_session.execute(insert(Reel).values(id=rid, org_id=org_id, reel_family_id=fid))
    db_session.execute(
        insert(Asset).values(id=aid, org_id=org_id, asset_class="clip", storage_uri="s3://b/a")
    )
    db_session.execute(
        insert(AssetPack).values(id=pack_id, org_id=org_id, name="Pack", niche="fitness")
    )
    db_session.execute(
        insert(AssetPackItem).values(
            id=uuid.uuid4(),
            asset_pack_id=pack_id,
            asset_id=aid,
            asset_kind="generated_clip",
            pack_role="background",
            status="selected",
        )
    )
    db_session.flush()
    db_session.execute(
        insert(AssetUsage).values(
            id=uuid.uuid4(),
            org_id=org_id,
            reel_id=rid,
            asset_id=aid,
            usage_role="background",
            component_role="background",
        )
    )
    db_session.flush()

    summaries = refresh_asset_usage_summaries(db_session, org_id=org_id, asset_ids=[aid])

    assert len(summaries) == 1
    summary = db_session.scalars(
        select(AssetUsageSummary).where(AssetUsageSummary.asset_id == aid)
    ).one()
    assert summary.reuse_count == 1
    assert summary.used_in_reel_count == 1
    assert summary.used_in_pack_count == 1
    assert summary.used_as_component_role_counts == {"background": 1}
    assert summary.last_used_at is not None


def test_reel_metric_rolls_up_asset_and_combination_performance(
    db_session: Session, org_id: uuid.UUID
) -> None:
    pid = uuid.uuid4()
    fid = uuid.uuid4()
    rid = uuid.uuid4()
    run_id = uuid.uuid4()
    hook_id = uuid.uuid4()
    background_id = uuid.uuid4()
    db_session.execute(
        insert(Page).values(id=pid, org_id=org_id, platform="instagram", display_name="Page")
    )
    db_session.execute(
        insert(ReelFamily).values(id=fid, org_id=org_id, page_id=pid, name="Family")
    )
    db_session.execute(insert(Reel).values(id=rid, org_id=org_id, reel_family_id=fid))
    db_session.execute(
        insert(Run).values(
            id=run_id,
            org_id=org_id,
            workflow_key="process_reel",
            input_params={"reel_id": str(rid)},
        )
    )
    for asset_id, uri in ((hook_id, "s3://b/hook"), (background_id, "s3://b/bg")):
        db_session.execute(
            insert(Asset).values(
                id=asset_id,
                org_id=org_id,
                asset_class="clip",
                storage_uri=uri,
            )
        )
    db_session.flush()
    db_session.execute(
        insert(AssetUsage).values(
            id=uuid.uuid4(),
            org_id=org_id,
            reel_id=rid,
            asset_id=hook_id,
            usage_role="hook",
            component_role="hook",
        )
    )
    db_session.execute(
        insert(AssetUsage).values(
            id=uuid.uuid4(),
            org_id=org_id,
            reel_id=rid,
            asset_id=background_id,
            usage_role="background",
            component_role="background",
        )
    )
    db_session.flush()
    metric = ReelMetric(
        org_id=org_id,
        run_id=run_id,
        metrics={"engagement_score": 0.8, "views": 100, "sample": True},
    )
    db_session.add(metric)
    db_session.flush()

    counts = aggregate_reel_metric_asset_performance(
        db_session,
        reel_metric_id=metric.id,
        combination_sizes=(2,),
    )

    assert counts == {"asset_summaries": 2, "combination_summaries": 1}
    hook_summary = db_session.scalars(
        select(AssetPerformanceSummary).where(
            AssetPerformanceSummary.asset_id == hook_id,
            AssetPerformanceSummary.component_role == "hook",
        )
    ).one()
    assert hook_summary.sample_count == 1
    assert hook_summary.metric_averages == {"engagement_score": 0.8, "views": 100.0}
    assert hook_summary.attribution_note == "correlational_not_causal"
    combo_summary = db_session.scalars(select(AssetCombinationPerformance)).one()
    assert combo_summary.sample_count == 1
    assert combo_summary.component_roles == ["background", "hook"]
    assert set(combo_summary.asset_ids) == {str(hook_id), str(background_id)}


def test_asset_family_fk_on_asset(db_session: Session, org_id: uuid.UUID) -> None:
    fid = uuid.uuid4()
    db_session.execute(insert(AssetFamily).values(id=fid, org_id=org_id, label="fam"))
    db_session.flush()
    db_session.execute(
        insert(Asset).values(
            id=uuid.uuid4(),
            org_id=org_id,
            family_id=fid,
            asset_class="clip",
            storage_uri="s3://b/fam",
        ),
    )
    db_session.flush()


def test_asset_pack_tracks_operator_defined_size_and_mix(
    db_session: Session, org_id: uuid.UUID
) -> None:
    pack_id = uuid.uuid4()
    db_session.execute(
        insert(AssetPack).values(
            id=pack_id,
            org_id=org_id,
            name="Pilates reusable kit",
            niche="pilates",
            purpose="Short-form reel backgrounds",
            target_audience="Busy beginners",
            requested_asset_count=8,
            asset_mix_requested_json={"generated_clip": 5, "image": 3},
            status="planned",
            strategy_summary="Focus on calm form demonstrations.",
        ),
    )
    db_session.flush()
    pack = db_session.scalars(select(AssetPack).where(AssetPack.id == pack_id)).one()
    assert pack.org_id == org_id
    assert pack.requested_asset_count == 8
    assert pack.asset_mix_requested_json == {"generated_clip": 5, "image": 3}
    assert pack.status == "planned"


def test_asset_pack_rejects_invalid_status(db_session: Session, org_id: uuid.UUID) -> None:
    with pytest.raises(IntegrityError):
        db_session.execute(
            insert(AssetPack).values(
                id=uuid.uuid4(),
                org_id=org_id,
                name="Bad pack",
                niche="fitness",
                status="unknown",
            ),
        )


def test_asset_pack_items_allow_asset_in_multiple_packs(
    db_session: Session, org_id: uuid.UUID
) -> None:
    aid = uuid.uuid4()
    pack_one_id = uuid.uuid4()
    pack_two_id = uuid.uuid4()
    db_session.execute(
        insert(Asset).values(
            id=aid,
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/reusable",
        ),
    )
    db_session.execute(
        insert(AssetPack).values(
            id=pack_one_id,
            org_id=org_id,
            name="Starter kit",
            niche="pilates",
        ),
    )
    db_session.execute(
        insert(AssetPack).values(
            id=pack_two_id,
            org_id=org_id,
            name="Advanced kit",
            niche="pilates",
        ),
    )
    db_session.flush()
    db_session.execute(
        insert(AssetPackItem).values(
            id=uuid.uuid4(),
            asset_pack_id=pack_one_id,
            asset_id=aid,
            asset_kind="generated_clip",
            pack_role="opener",
            reuse_purpose="Hook visual",
            priority=1,
            status="selected",
            metadata_json={"selected_from": "library"},
        ),
    )
    db_session.execute(
        insert(AssetPackItem).values(
            id=uuid.uuid4(),
            asset_pack_id=pack_two_id,
            asset_id=aid,
            asset_kind="generated_clip",
            pack_role="transition",
            reuse_purpose="Mid-reel reset",
            priority=2,
            status="selected",
        ),
    )
    db_session.flush()
    rows = db_session.scalars(select(AssetPackItem).where(AssetPackItem.asset_id == aid)).all()
    assert len(rows) == 2
    assert {row.asset_pack_id for row in rows} == {pack_one_id, pack_two_id}


def test_asset_pack_item_can_be_planned_before_asset_exists(
    db_session: Session, org_id: uuid.UUID
) -> None:
    pack_id = uuid.uuid4()
    planned_spec_id = uuid.uuid4()
    item_id = uuid.uuid4()
    db_session.execute(
        insert(AssetPack).values(
            id=pack_id,
            org_id=org_id,
            name="Upload queue",
            niche="travel",
        ),
    )
    db_session.flush()
    db_session.execute(
        insert(PlannedAssetSpec).values(
            id=planned_spec_id,
            asset_pack_id=pack_id,
            asset_kind="voiceover",
            media_type="audio",
            working_title="Narration bed",
            purpose="Reusable voiceover placeholder",
            prompt_or_description="Warm narration for travel reels",
            status="planned",
        ),
    )
    db_session.flush()
    db_session.execute(
        insert(AssetPackItem).values(
            id=item_id,
            asset_pack_id=pack_id,
            planned_asset_spec_id=planned_spec_id,
            asset_kind="voiceover",
            pack_role="narration",
            status="planned",
        ),
    )
    db_session.flush()
    item = db_session.scalars(select(AssetPackItem).where(AssetPackItem.id == item_id)).one()
    assert item.asset_id is None
    assert item.planned_asset_spec_id == planned_spec_id
    assert item.status == "planned"


def test_planned_asset_spec_holds_pack_plan_before_asset_exists(
    db_session: Session, org_id: uuid.UUID
) -> None:
    pack_id = uuid.uuid4()
    spec_id = uuid.uuid4()
    db_session.execute(
        insert(AssetPack).values(
            id=pack_id,
            org_id=org_id,
            name="Intentional travel kit",
            niche="travel",
            requested_asset_count=3,
            status="planned",
        ),
    )
    db_session.flush()
    db_session.execute(
        insert(PlannedAssetSpec).values(
            id=spec_id,
            asset_pack_id=pack_id,
            asset_kind="generated_clip",
            media_type="video",
            working_title="Cafe reveal",
            purpose="Reusable scene-setter",
            prompt_or_description="Slow handheld reveal of a quiet cafe exterior",
            required_traits={"camera": "handheld", "mood": "warm"},
            compatible_with={"niches": ["travel", "lifestyle"]},
            intended_reel_formats=["hook", "transition"],
            priority=2,
            estimated_reuse_count=6,
            status="planned",
        ),
    )
    db_session.flush()
    spec = db_session.scalars(select(PlannedAssetSpec).where(PlannedAssetSpec.id == spec_id)).one()
    assert spec.asset_pack_id == pack_id
    assert spec.required_traits == {"camera": "handheld", "mood": "warm"}
    assert spec.compatible_with == {"niches": ["travel", "lifestyle"]}
    assert spec.intended_reel_formats == ["hook", "transition"]
    assert spec.estimated_reuse_count == 6
    assert spec.status == "planned"


def test_planned_asset_spec_rejects_invalid_status(db_session: Session, org_id: uuid.UUID) -> None:
    pack_id = uuid.uuid4()
    db_session.execute(
        insert(AssetPack).values(
            id=pack_id,
            org_id=org_id,
            name="Bad spec pack",
            niche="travel",
        ),
    )
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(
            insert(PlannedAssetSpec).values(
                id=uuid.uuid4(),
                asset_pack_id=pack_id,
                asset_kind="generated_clip",
                media_type="video",
                working_title="Bad status",
                purpose="Exercise the status check",
                prompt_or_description="Bad status",
                status="ready",
            ),
        )


def test_planned_asset_spec_status_transition_guard() -> None:
    validate_planned_asset_spec_status_transition("draft", "planned")
    validate_planned_asset_spec_status_transition("planned", "generating")
    validate_planned_asset_spec_status_transition("generating", "generated")
    validate_planned_asset_spec_status_transition("generated", "registered")
    validate_planned_asset_spec_status_transition("failed", "planned")
    with pytest.raises(ValueError):
        validate_planned_asset_spec_status_transition("draft", "registered")
    with pytest.raises(ValueError):
        validate_planned_asset_spec_status_transition("archived", "planned")


def test_asset_pack_item_traces_asset_back_to_planned_spec(
    db_session: Session, org_id: uuid.UUID
) -> None:
    aid = uuid.uuid4()
    pack_id = uuid.uuid4()
    spec_id = uuid.uuid4()
    item_id = uuid.uuid4()
    db_session.execute(
        insert(Asset).values(
            id=aid,
            org_id=org_id,
            asset_class="clip",
            storage_uri="s3://b/generated-from-spec",
        ),
    )
    db_session.execute(
        insert(AssetPack).values(
            id=pack_id,
            org_id=org_id,
            name="Traceable kit",
            niche="pilates",
        ),
    )
    db_session.flush()
    db_session.execute(
        insert(PlannedAssetSpec).values(
            id=spec_id,
            asset_pack_id=pack_id,
            asset_kind="generated_clip",
            media_type="video",
            working_title="Form detail",
            purpose="Reusable close-up for technique reels",
            prompt_or_description="Close-up of controlled pilates form",
            status="registered",
        ),
    )
    db_session.flush()
    db_session.execute(
        insert(AssetPackItem).values(
            id=item_id,
            asset_pack_id=pack_id,
            planned_asset_spec_id=spec_id,
            asset_id=aid,
            asset_kind="generated_clip",
            pack_role="technique_closeup",
            reuse_purpose="Show intentional form detail",
            status="generated",
        ),
    )
    db_session.flush()
    item = db_session.scalars(select(AssetPackItem).where(AssetPackItem.id == item_id)).one()
    assert item.asset_id == aid
    assert item.planned_asset_spec_id == spec_id
    assert item.planned_asset_spec is not None
    assert item.planned_asset_spec.purpose == "Reusable close-up for technique reels"
