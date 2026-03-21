"""Tests for phase-1 operational ORM tables and Alembic revision chain."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Table

from content_lab_api.models import Asset, OutboxEvent, Run

API_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_single_head_is_0008() -> None:
    """Migration smoke: revision graph loads and head is 0008 (linear merged history)."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["0008"]


def test_alembic_down_revision_chain() -> None:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    rev = script.get_revision("0004")
    assert rev is not None
    assert rev.down_revision == "0003"
    rev3 = script.get_revision("0003")
    assert rev3 is not None
    assert rev3.down_revision == "0002"


def _partial_unique_index_names(table: Table) -> set[str]:
    names: set[str] = set()
    for ix in table.indexes:
        if not ix.unique:
            continue
        opts: dict[str, Any] = dict(ix.dialect_options.get("postgresql", {}))
        if opts.get("where") is not None:
            names.add(str(ix.name))
    return names


def test_asset_org_scoped_asset_key_uniqueness_index() -> None:
    partial = _partial_unique_index_names(cast(Table, Asset.__table__))
    assert "uq_assets_org_asset_key" in partial


def test_run_org_scoped_idempotency_uniqueness_index() -> None:
    partial = _partial_unique_index_names(cast(Table, Run.__table__))
    assert "uq_runs_org_idempotency_key" in partial


def test_outbox_dispatch_queue_partial_index() -> None:
    tbl = cast(Table, OutboxEvent.__table__)
    ix = next(i for i in tbl.indexes if str(i.name) == "ix_outbox_events_dispatch_queue")
    opts: dict[str, Any] = dict(ix.dialect_options.get("postgresql", {}))
    assert opts.get("where") is not None


def test_asset_default_field_values() -> None:
    org_id = uuid.uuid4()
    asset = Asset(org_id=org_id, asset_class="image", storage_uri="s3://bucket/key")
    assert asset.source == "unknown"
    assert asset.status == "active"
    assert asset.asset_key is None
    assert asset.content_hash is None
    assert asset.phash is None


def test_run_default_field_values() -> None:
    org_id = uuid.uuid4()
    run = Run(org_id=org_id, workflow_key="process_reel")
    assert run.flow_trigger == "unknown"
    assert run.idempotency_key is None
    assert run.external_ref is None
    assert run.started_at is None
    assert run.finished_at is None
    assert run.run_metadata == {}


def test_outbox_default_field_values() -> None:
    org_id = uuid.uuid4()
    evt = OutboxEvent(
        org_id=org_id,
        aggregate_type="run",
        aggregate_id="a1",
        event_type="completed",
    )
    assert evt.delivery_status == "pending"
    assert evt.attempt_count == 0
    assert evt.next_attempt_at is None
    assert evt.dispatched_at is None


@pytest.mark.parametrize(
    "module_path",
    [
        "migrations.versions.0004_expand_operational_tables",
    ],
)
def test_migration_module_defines_expected_revisions(module_path: str) -> None:
    """Ensure the new migration file is syntactically valid and exposes revision ids."""
    parts = module_path.rsplit(".", 1)
    assert len(parts) == 2
    _pkg, mod_name = parts
    versions_dir = API_ROOT / "migrations" / "versions"
    path = versions_dir / f"{mod_name}.py"
    assert path.is_file(), f"missing migration file {path}"
    spec = importlib.util.spec_from_file_location(module_path, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0004"
    assert module.down_revision == "0003"
