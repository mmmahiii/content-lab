"""asset usage and performance summaries

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_usage_summaries",
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
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reuse_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_in_reel_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_in_pack_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "used_as_component_role_counts",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("org_id", "asset_id", name="uq_asset_usage_summaries_org_asset"),
    )
    op.create_index(
        "ix_asset_usage_summaries_org_last_used",
        "asset_usage_summaries",
        ["org_id", "last_used_at"],
    )

    op.create_table(
        "asset_performance_summaries",
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
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("component_role", sa.String(64), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "metric_totals",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metric_averages",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_metric_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attribution_note",
            sa.String(128),
            nullable=False,
            server_default="correlational_not_causal",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "org_id",
            "asset_id",
            "component_role",
            name="uq_asset_performance_summaries_org_asset_role",
        ),
    )
    op.create_index(
        "ix_asset_performance_summaries_org_role",
        "asset_performance_summaries",
        ["org_id", "component_role"],
    )

    op.create_table(
        "asset_combination_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("combination_key", sa.String(512), nullable=False),
        sa.Column(
            "component_roles",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "asset_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "metric_totals",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metric_averages",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_metric_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attribution_note",
            sa.String(128),
            nullable=False,
            server_default="correlational_not_causal",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "org_id",
            "combination_key",
            name="uq_asset_combination_performance_org_key",
        ),
    )
    op.create_index(
        "ix_asset_combination_performance_org_sample_count",
        "asset_combination_performance",
        ["org_id", "sample_count"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asset_combination_performance_org_sample_count",
        table_name="asset_combination_performance",
    )
    op.drop_table("asset_combination_performance")
    op.drop_index(
        "ix_asset_performance_summaries_org_role",
        table_name="asset_performance_summaries",
    )
    op.drop_table("asset_performance_summaries")
    op.drop_index(
        "ix_asset_usage_summaries_org_last_used",
        table_name="asset_usage_summaries",
    )
    op.drop_table("asset_usage_summaries")
