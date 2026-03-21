"""policy, experiments, tasks, provider jobs, audit, storage integrity

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_key", sa.String(128), nullable=False),
        sa.Column("state", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("org_id", "policy_key", name="uq_policy_state_org_policy_key"),
    )
    op.create_index("ix_policy_state_org_id", "policy_state", ["org_id"])

    op.create_table(
        "experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("experiment_key", sa.String(128), nullable=False),
        sa.Column("variant", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(256), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "org_id",
            "experiment_key",
            "subject_type",
            "subject_id",
            name="uq_experiments_org_experiment_subject",
        ),
    )
    op.create_index("ix_experiments_org_id", "experiments", ["org_id"])

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("org_id", "idempotency_key", name="uq_tasks_org_idempotency_key"),
    )
    op.create_index("ix_tasks_org_id", "tasks", ["org_id"])
    op.create_index("ix_tasks_run_id", "tasks", ["run_id"])

    op.create_table(
        "provider_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("external_ref", sa.String(512), nullable=False),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "provider", "external_ref", name="uq_provider_jobs_provider_external_ref"
        ),
    )
    op.create_index("ix_provider_jobs_org_id", "provider_jobs", ["org_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(64), nullable=True),
        sa.Column("actor_id", sa.String(256), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(128), nullable=False),
        sa.Column("resource_id", sa.String(256), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_audit_log_org_id_created_at", "audit_log", ["org_id", "created_at"])

    op.create_table(
        "storage_integrity_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("check_kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("detail", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_storage_integrity_checks_org_id_status",
        "storage_integrity_checks",
        ["org_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_storage_integrity_checks_org_id_status", table_name="storage_integrity_checks"
    )
    op.drop_table("storage_integrity_checks")

    op.drop_index("ix_audit_log_org_id_created_at", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_provider_jobs_org_id", table_name="provider_jobs")
    op.drop_table("provider_jobs")

    op.drop_index("ix_tasks_run_id", table_name="tasks")
    op.drop_index("ix_tasks_org_id", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_experiments_org_id", table_name="experiments")
    op.drop_table("experiments")

    op.drop_index("ix_policy_state_org_id", table_name="policy_state")
    op.drop_table("policy_state")
