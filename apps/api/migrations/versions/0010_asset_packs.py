"""asset packs and pack item membership

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("niche", sa.String(256), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("requested_asset_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("asset_mix_requested_json", postgresql.JSONB, nullable=True),
        sa.Column("asset_mix_final_json", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("strategy_summary", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('draft', 'planned', 'generating', 'ready', 'failed', 'archived')",
            name="ck_asset_packs_status",
        ),
        sa.CheckConstraint(
            "requested_asset_count >= 0",
            name="ck_asset_packs_requested_asset_count_nonnegative",
        ),
    )
    op.create_index("ix_asset_packs_org_id", "asset_packs", ["org_id"])
    op.create_index(
        "ix_asset_packs_org_status",
        "asset_packs",
        ["org_id", "status"],
    )

    op.create_table(
        "asset_pack_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_pack_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_packs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("planned_asset_spec_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("asset_kind", sa.String(64), nullable=False),
        sa.Column("pack_role", sa.String(128), nullable=False),
        sa.Column("reuse_purpose", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("metadata_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'generating', 'generated', 'uploaded', 'imported', "
            "'reused', 'selected', 'failed')",
            name="ck_asset_pack_items_status",
        ),
    )
    op.create_index(
        "ix_asset_pack_items_asset_pack_id",
        "asset_pack_items",
        ["asset_pack_id"],
    )
    op.create_index("ix_asset_pack_items_asset_id", "asset_pack_items", ["asset_id"])
    op.create_index(
        "ix_asset_pack_items_pack_status",
        "asset_pack_items",
        ["asset_pack_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_asset_pack_items_pack_status", table_name="asset_pack_items")
    op.drop_index("ix_asset_pack_items_asset_id", table_name="asset_pack_items")
    op.drop_index("ix_asset_pack_items_asset_pack_id", table_name="asset_pack_items")
    op.drop_table("asset_pack_items")

    op.drop_index("ix_asset_packs_org_status", table_name="asset_packs")
    op.drop_index("ix_asset_packs_org_id", table_name="asset_packs")
    op.drop_table("asset_packs")
