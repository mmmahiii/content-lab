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

from content_lab_api.models import (
    Asset,
    AssetPack,
    AssetPackItem,
    OutboxEvent,
    PlannedAssetSpec,
    Run,
)

API_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_single_head_is_0012() -> None:
    """Migration smoke: revision graph loads and head is 0012."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["0012"]


def test_alembic_down_revision_chain() -> None:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    rev = script.get_revision("0004")
    assert rev is not None
    assert rev.down_revision == "0003"
    rev3 = script.get_revision("0003")
    assert rev3 is not None
    assert rev3.down_revision == "0002"
    rev10 = script.get_revision("0010")
    assert rev10 is not None
    assert rev10.down_revision == "0009"
    rev11 = script.get_revision("0011")
    assert rev11 is not None
    assert rev11.down_revision == "0010"
    rev12 = script.get_revision("0012")
    assert rev12 is not None
    assert rev12.down_revision == "0011"


def _partial_unique_index_names(table: Table) -> set[str]:
    names: set[str] = set()
    for ix in table.indexes:
        if not ix.unique:
            continue
        opts: dict[str, Any] = dict(ix.dialect_options.get("postgresql", {}))
        if opts.get("where") is not None:
            names.add(str(ix.name))
    return names


def test_asset_org_scoped_asset_key_hash_uniqueness_index() -> None:
    partial = _partial_unique_index_names(cast(Table, Asset.__table__))
    assert "uq_assets_org_asset_key_hash" in partial
    assert "uq_assets_org_asset_key" not in partial


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


def test_asset_pack_default_field_values() -> None:
    org_id = uuid.uuid4()
    pack = AssetPack(org_id=org_id, name="Fitness hooks", niche="fitness")
    assert pack.status == "draft"
    assert pack.requested_asset_count == 0
    assert pack.purpose is None
    assert pack.target_audience is None
    assert pack.asset_mix_requested_json is None
    assert pack.asset_mix_final_json is None
    assert pack.strategy_summary is None


def test_asset_pack_item_default_field_values() -> None:
    pack_id = uuid.uuid4()
    item = AssetPackItem(
        asset_pack_id=pack_id,
        asset_kind="generated_clip",
        pack_role="background_b_roll",
    )
    assert item.asset_id is None
    assert item.planned_asset_spec_id is None
    assert item.reuse_purpose is None
    assert item.priority == 0
    assert item.status == "planned"
    assert item.metadata_json == {}


def test_planned_asset_spec_default_field_values() -> None:
    pack_id = uuid.uuid4()
    spec = PlannedAssetSpec(
        asset_pack_id=pack_id,
        asset_kind="generated_clip",
        media_type="video",
        working_title="Mat opener",
        purpose="Reusable opening shot",
        prompt_or_description="A calm mat pilates opening shot",
    )
    assert spec.required_traits == {}
    assert spec.compatible_with == {}
    assert spec.intended_reel_formats == []
    assert spec.priority == 0
    assert spec.estimated_reuse_count == 0
    assert spec.status == "draft"


def test_asset_key_column_uses_text_storage() -> None:
    asset_key_column = cast(Table, Asset.__table__).c.asset_key
    assert asset_key_column.type.__class__.__name__ == "Text"


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
        "migrations.versions.0010_asset_packs",
        "migrations.versions.0011_planned_asset_specs",
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
    expected = {
        "0004_expand_operational_tables": ("0004", "0003"),
        "0010_asset_packs": ("0010", "0009"),
        "0011_planned_asset_specs": ("0011", "0010"),
    }
    assert module.revision == expected[mod_name][0]
    assert module.down_revision == expected[mod_name][1]
