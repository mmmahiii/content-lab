"""expand operational tables for phase-1 semantics

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- assets: registry-oriented fields + org-scoped AssetKey uniqueness ---
    op.add_column(
        "assets",
        sa.Column("source", sa.String(length=64), nullable=False, server_default="unknown"),
    )
    op.add_column("assets", sa.Column("asset_key", sa.String(length=512), nullable=True))
    op.add_column("assets", sa.Column("content_hash", sa.String(length=128), nullable=True))
    op.add_column(
        "assets",
        sa.Column("phash", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.create_index(
        "uq_assets_org_asset_key",
        "assets",
        ["org_id", "asset_key"],
        unique=True,
        postgresql_where=sa.text("asset_key IS NOT NULL"),
    )

    # --- runs: flow trigger, idempotency, timing, metadata ---
    op.add_column(
        "runs",
        sa.Column("flow_trigger", sa.String(length=64), nullable=False, server_default="unknown"),
    )
    op.add_column("runs", sa.Column("idempotency_key", sa.String(length=256), nullable=True))
    op.add_column("runs", sa.Column("external_ref", sa.String(length=512), nullable=True))
    op.add_column(
        "runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column(
            "run_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "uq_runs_org_idempotency_key",
        "runs",
        ["org_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # --- outbox: delivery state, retries, next attempt ---
    op.add_column(
        "outbox_events",
        sa.Column(
            "delivery_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "outbox_events",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE outbox_events SET delivery_status = 'sent', attempt_count = 1 "
        "WHERE dispatched_at IS NOT NULL"
    )
    op.execute(
        "UPDATE outbox_events SET delivery_status = 'pending', attempt_count = 0 "
        "WHERE dispatched_at IS NULL"
    )
    op.drop_index("ix_outbox_events_undispatched", table_name="outbox_events")
    op.create_index(
        "ix_outbox_events_dispatch_queue",
        "outbox_events",
        ["next_attempt_at", "created_at"],
        postgresql_where=sa.text("delivery_status IN ('pending', 'failed')"),
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_dispatch_queue", table_name="outbox_events")
    op.create_index(
        "ix_outbox_events_undispatched",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("dispatched_at IS NULL"),
    )
    op.drop_column("outbox_events", "next_attempt_at")
    op.drop_column("outbox_events", "attempt_count")
    op.drop_column("outbox_events", "delivery_status")

    op.drop_index("uq_runs_org_idempotency_key", table_name="runs")
    op.drop_column("runs", "run_metadata")
    op.drop_column("runs", "finished_at")
    op.drop_column("runs", "started_at")
    op.drop_column("runs", "external_ref")
    op.drop_column("runs", "idempotency_key")
    op.drop_column("runs", "flow_trigger")

    op.drop_index("uq_assets_org_asset_key", table_name="assets")
    op.drop_column("assets", "status")
    op.drop_column("assets", "phash")
    op.drop_column("assets", "content_hash")
    op.drop_column("assets", "asset_key")
    op.drop_column("assets", "source")
