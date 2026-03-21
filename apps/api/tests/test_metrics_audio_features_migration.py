"""Migration smoke and DB round-trips for intelligence-phase tables (DB-005)."""

from __future__ import annotations

import importlib.util
import io
import os
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

API_ROOT = Path(__file__).resolve().parents[1]


def _default_database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://contentlab:contentlab@127.0.0.1:5433/contentlab",
    )


def _postgres_ready() -> bool:
    try:
        engine = create_engine(_default_database_url(), pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except OSError:
        return False
    except Exception:
        return False


def _alembic_config(database_url: str | None = None) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _load_migration_0006() -> ModuleType:
    path = API_ROOT / "migrations" / "versions" / "0006_metrics_audio_features.py"
    spec = importlib.util.spec_from_file_location("migration_0006", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_0006_migration_revision_metadata() -> None:
    m = _load_migration_0006()
    assert m.revision == "0006"
    assert m.down_revision == "0005"


def test_0006_upgrade_emits_ddl_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline SQL generation (no live Postgres required)."""
    monkeypatch.chdir(API_ROOT)
    buf = io.StringIO()
    cfg = _alembic_config()
    with redirect_stdout(buf):
        command.upgrade(cfg, "0006", sql=True)
    sql = buf.getvalue().lower()
    assert "reel_metrics" in sql
    assert "audio" in sql
    assert "features" in sql
    assert "embedding" in sql


@pytest.mark.skipif(not _postgres_ready(), reason="Postgres not reachable")
def test_reel_metrics_snapshot_and_nullable_feature_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inserts into new tables; core package tables are not required for these rows."""
    url = _default_database_url()
    cfg = _alembic_config(url)
    monkeypatch.chdir(API_ROOT)
    command.upgrade(cfg, "head")

    from content_lab_api.models.asset import Asset
    from content_lab_api.models.audio_track import AudioTrack
    from content_lab_api.models.derived_feature import DerivedFeature
    from content_lab_api.models.reel_metric import ReelMetric
    from content_lab_api.models.run import Run

    engine = create_engine(url, pool_pre_ping=True)
    SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    org_id = uuid.UUID("00000000-0000-4000-8000-000000000001")
    with SessionFactory() as session:
        run = Run(org_id=org_id, workflow_key="integration-test-run", status="pending")
        asset = Asset(
            org_id=org_id,
            asset_class="video",
            storage_uri="s3://test-bucket/reel.mp4",
        )
        session.add(run)
        session.add(asset)
        session.flush()
        run_id = run.id
        asset_id = asset.id

        snapshot = ReelMetric(
            org_id=org_id,
            run_id=run_id,
            metrics={"engagement_score": 0.42, "sample": True},
            extractor_version="test-1",
        )
        track = AudioTrack(
            org_id=org_id,
            asset_id=asset_id,
            duration_seconds=10.5,
            sample_rate_hz=48_000,
            channel_count=2,
            codec="aac",
            extra={"loudness_lufs": -14.0},
        )
        feature_row = DerivedFeature(
            org_id=org_id,
            asset_id=asset_id,
            feature_kind="scene",
            dimensions={"frame_count": 3},
            embedding=None,
        )
        session.add_all([snapshot, track, feature_row])
        rid = snapshot.id
        fid = feature_row.id
        tid = track.id
        session.commit()

    with SessionFactory() as session:
        loaded = session.get(ReelMetric, rid)
        assert loaded is not None
        assert loaded.metrics["engagement_score"] == 0.42
        feat = session.get(DerivedFeature, fid)
        assert feat is not None
        assert feat.embedding is None

    with SessionFactory() as session:
        session.delete(session.get(ReelMetric, rid))
        session.delete(session.get(DerivedFeature, fid))
        session.delete(session.get(AudioTrack, tid))
        session.delete(session.get(Run, run_id))
        session.delete(session.get(Asset, asset_id))
        session.commit()

    engine.dispose()
