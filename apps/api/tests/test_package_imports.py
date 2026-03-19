"""Smoke tests verifying the refactored package layout is importable."""


def test_import_models() -> None:
    from content_lab_api.models import Asset, OutboxEvent, Run, RunAsset

    assert Asset.__tablename__ == "assets"
    assert Run.__tablename__ == "runs"
    assert RunAsset.__tablename__ == "run_assets"
    assert OutboxEvent.__tablename__ == "outbox_events"


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
