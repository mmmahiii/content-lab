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
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from content_lab_api.models import Org, ProviderJob, Task

API_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_FILE = (
    API_ROOT / "migrations" / "versions" / "0008_policy_tasks_provider_audit_integrity.py"
)


def _integration_database_url() -> str:
    """Prefer dedicated integration URL; otherwise use the same DB as the rest of the API tests."""
    explicit = os.environ.get("CONTENT_LAB_INTEGRATION_DATABASE_URL")
    if explicit:
        return explicit
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://contentlab:contentlab@127.0.0.1:5433/contentlab",
    )


def _integration_engine_or_skip() -> Engine:
    """Return an engine to the integration DB, or skip if Postgres is unreachable (fast timeout)."""
    url = _integration_database_url()
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable ({url!r}): {exc}")
    return engine


def test_revision_0008_module_wires_alembic_chain() -> None:
    spec = importlib.util.spec_from_file_location("content_lab_alembic_0008", MIGRATION_FILE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0008"
    assert mod.down_revision == "0007"


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


def test_migration_smoke_tables_exist_after_upgrade() -> None:
    engine = _integration_engine_or_skip()
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


def test_task_idempotency_key_unique_per_org() -> None:
    engine = _integration_engine_or_skip()
    SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with SessionFactory() as session:
        org = Org(name="DB-0008 tasks", slug=f"db0008-task-{uuid.uuid4().hex[:12]}")
        session.add(org)
        session.flush()
        org_id = org.id
        first = Task(
            org_id=org_id,
            task_type="integration",
            idempotency_key=f"idem-{uuid.uuid4()}",
        )
        session.add(first)
        session.flush()
        dup = Task(
            org_id=org_id,
            task_type="integration",
            idempotency_key=first.idempotency_key,
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_provider_job_external_ref_unique_per_provider() -> None:
    engine = _integration_engine_or_skip()
    SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    external_ref = f"ext-{uuid.uuid4()}"
    with SessionFactory() as session:
        org = Org(name="DB-0008 provider_jobs", slug=f"db0008-pj-{uuid.uuid4().hex[:12]}")
        session.add(org)
        session.flush()
        org_id = org.id
        first = ProviderJob(
            org_id=org_id,
            provider="test-provider",
            external_ref=external_ref,
        )
        session.add(first)
        session.flush()
        dup = ProviderJob(
            org_id=org_id,
            provider="test-provider",
            external_ref=external_ref,
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
