"""DB-007: migration revision metadata, ORM constraints, and optional live DB checks."""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from typing import cast

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Table, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from content_lab_api.models import ProviderJob, Task

API_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_FILE = (
    API_ROOT / "migrations" / "versions" / "0008_policy_tasks_provider_audit_integrity.py"
)

DEFAULT_ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def _integration_database_url() -> str | None:
    return os.environ.get("CONTENT_LAB_INTEGRATION_DATABASE_URL")


requires_integration_db = pytest.mark.skipif(
    _integration_database_url() is None,
    reason="Set CONTENT_LAB_INTEGRATION_DATABASE_URL to exercise migrations and DB uniqueness.",
)


def test_revision_0008_module_wires_alembic_chain() -> None:
    spec = importlib.util.spec_from_file_location("content_lab_alembic_0008", MIGRATION_FILE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0008"
    assert mod.down_revision == "0003"


def test_alembic_script_head_is_0008() -> None:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["0008"]


def test_task_table_has_org_idempotency_unique_constraint() -> None:
    task_table = cast(Table, Task.__table__)
    names = {c.name for c in task_table.constraints if c.name}
    assert "uq_tasks_org_idempotency_key" in names


def test_provider_jobs_table_has_provider_external_ref_unique_constraint() -> None:
    provider_jobs_table = cast(Table, ProviderJob.__table__)
    names = {c.name for c in provider_jobs_table.constraints if c.name}
    assert "uq_provider_jobs_provider_external_ref" in names


@requires_integration_db
def test_migration_smoke_tables_exist_after_upgrade() -> None:
    url = _integration_database_url()
    assert url
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    insp = inspect(engine)
    for table in (
        "policy_state",
        "experiments",
        "tasks",
        "provider_jobs",
        "audit_log",
        "storage_integrity_checks",
    ):
        assert insp.has_table(table), f"missing table {table}"


@requires_integration_db
def test_task_idempotency_key_unique_per_org() -> None:
    url = _integration_database_url()
    assert url
    engine = create_engine(url, pool_pre_ping=True)
    SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with SessionFactory() as session:
        first = Task(
            org_id=DEFAULT_ORG_ID,
            task_type="integration",
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        session.add(first)
        session.flush()
        dup = Task(
            org_id=DEFAULT_ORG_ID,
            task_type="integration",
            idempotency_key=first.idempotency_key,
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


@requires_integration_db
def test_provider_job_external_ref_unique_per_provider() -> None:
    url = _integration_database_url()
    assert url
    engine = create_engine(url, pool_pre_ping=True)
    SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    external_ref = f"ext-{uuid.uuid4()}"
    with SessionFactory() as session:
        first = ProviderJob(
            org_id=DEFAULT_ORG_ID,
            provider="test-provider",
            external_ref=external_ref,
        )
        session.add(first)
        session.flush()
        dup = ProviderJob(
            org_id=DEFAULT_ORG_ID,
            provider="test-provider",
            external_ref=external_ref,
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
