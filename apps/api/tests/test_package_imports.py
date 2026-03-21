"""Smoke tests verifying the refactored package layout is importable."""


def test_import_models() -> None:
    from content_lab_api.models import Asset, OutboxEvent, Page, Reel, ReelFamily, Run, RunAsset

    assert Asset.__tablename__ == "assets"
    assert Page.__tablename__ == "pages"
    assert ReelFamily.__tablename__ == "reel_families"
    assert Reel.__tablename__ == "reels"
    assert Run.__tablename__ == "runs"
    assert RunAsset.__tablename__ == "run_assets"
    assert OutboxEvent.__tablename__ == "outbox_events"
    assert "asset_class" in Asset.__table__.c
    assert "storage_uri" in Asset.__table__.c
    assert "workflow_key" in Run.__table__.c
    assert "dispatched_at" in OutboxEvent.__table__.c
    assert "asset_role" in RunAsset.__table__.c


def test_import_schemas() -> None:
    from content_lab_api.schemas import (
        AssetCreate,
        AssetOut,
        OutboxEventOut,
        RunCreate,
        RunOut,
    )

    for cls in (AssetCreate, AssetOut, OutboxEventOut, RunCreate, RunOut):
        assert issubclass(cls, object)


def test_import_deps() -> None:
    from content_lab_api.deps import get_db

    assert callable(get_db)


def test_import_routes() -> None:
    from content_lab_api.routes import api_router

    paths = [getattr(r, "path", None) for r in api_router.routes]
    assert "/health" in paths


def test_import_db_base() -> None:
    from content_lab_api.db import Base

    assert hasattr(Base, "metadata")


def test_entrypoint_app() -> None:
    from content_lab_api.main import app

    assert app.title == "Content Lab API"
