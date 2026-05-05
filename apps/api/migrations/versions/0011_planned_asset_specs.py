"""planned asset specs for intentional pack planning

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planned_asset_specs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_pack_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_packs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_kind", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(64), nullable=False),
        sa.Column("working_title", sa.String(256), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("prompt_or_description", sa.Text(), nullable=False),
        sa.Column("required_traits", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("compatible_with", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("intended_reel_formats", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_reuse_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
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
            "status IN ('draft', 'planned', 'generating', 'generated', 'registered', "
            "'failed', 'archived')",
            name="ck_planned_asset_specs_status",
        ),
        sa.CheckConstraint(
            "priority >= 0",
            name="ck_planned_asset_specs_priority_nonnegative",
        ),
        sa.CheckConstraint(
            "estimated_reuse_count >= 0",
            name="ck_planned_asset_specs_estimated_reuse_count_nonnegative",
        ),
    )
    op.create_index(
        "ix_planned_asset_specs_asset_pack_id",
        "planned_asset_specs",
        ["asset_pack_id"],
    )
    op.create_index(
        "ix_planned_asset_specs_pack_status",
        "planned_asset_specs",
        ["asset_pack_id", "status"],
    )

    op.execute("UPDATE asset_pack_items SET planned_asset_spec_id = NULL")
    op.create_foreign_key(
        "fk_asset_pack_items_planned_asset_spec_id",
        "asset_pack_items",
        "planned_asset_specs",
        ["planned_asset_spec_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_asset_pack_items_planned_asset_spec_id",
        "asset_pack_items",
        ["planned_asset_spec_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asset_pack_items_planned_asset_spec_id",
        table_name="asset_pack_items",
    )
    op.drop_constraint(
        "fk_asset_pack_items_planned_asset_spec_id",
        "asset_pack_items",
        type_="foreignkey",
    )
    op.drop_index("ix_planned_asset_specs_pack_status", table_name="planned_asset_specs")
    op.drop_index("ix_planned_asset_specs_asset_pack_id", table_name="planned_asset_specs")
    op.drop_table("planned_asset_specs")
