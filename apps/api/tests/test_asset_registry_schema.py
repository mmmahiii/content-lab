"""Schema-level checks for asset registry tables (requires migrated PostgreSQL)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from content_lab_api.models import (
    Asset,
    AssetFamily,
    AssetGenParam,
    AssetUsage,
    Org,
    Page,
    Reel,
    ReelFamily,
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
        ),
    )
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
