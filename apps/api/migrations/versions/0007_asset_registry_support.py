"""asset registry support: families, gen params, usage lineage, asset key hash

Revision ID: 0007
Revises: 0003
Create Date: 2026-03-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_families",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_asset_families_org_id", "asset_families", ["org_id"])

    op.create_table(
        "reels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_reels_org_id", "reels", ["org_id"])

    op.add_column(
        "assets",
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_families.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("assets", sa.Column("asset_key_hash", sa.String(64), nullable=True))
    op.create_index(
        "uq_assets_org_asset_key_hash",
        "assets",
        ["org_id", "asset_key_hash"],
        unique=True,
        postgresql_where=sa.text("asset_key_hash IS NOT NULL"),
    )
    op.create_index("ix_assets_family_id", "assets", ["family_id"])

    op.create_table(
        "asset_gen_params",
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
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("canonical_params", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("asset_key_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("asset_id", "seq", name="uq_asset_gen_params_asset_seq"),
    )
    op.create_index("ix_asset_gen_params_org_id", "asset_gen_params", ["org_id"])
    op.create_index("ix_asset_gen_params_asset_id", "asset_gen_params", ["asset_id"])
    op.create_index(
        "ix_asset_gen_params_org_asset_key_hash",
        "asset_gen_params",
        ["org_id", "asset_key_hash"],
    )

    op.create_table(
        "asset_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("usage_role", sa.String(64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "reel_id",
            "asset_id",
            "usage_role",
            name="uq_asset_usage_reel_asset_role",
        ),
    )
    op.create_index("ix_asset_usage_org_id", "asset_usage", ["org_id"])
    op.create_index("ix_asset_usage_reel_id", "asset_usage", ["reel_id"])
    op.create_index("ix_asset_usage_asset_id", "asset_usage", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_asset_usage_asset_id", table_name="asset_usage")
    op.drop_index("ix_asset_usage_reel_id", table_name="asset_usage")
    op.drop_index("ix_asset_usage_org_id", table_name="asset_usage")
    op.drop_table("asset_usage")

    op.drop_index("ix_asset_gen_params_org_asset_key_hash", table_name="asset_gen_params")
    op.drop_index("ix_asset_gen_params_asset_id", table_name="asset_gen_params")
    op.drop_index("ix_asset_gen_params_org_id", table_name="asset_gen_params")
    op.drop_table("asset_gen_params")

    op.drop_index("ix_assets_family_id", table_name="assets")
    op.drop_index("uq_assets_org_asset_key_hash", table_name="assets")
    op.drop_column("assets", "asset_key_hash")
    op.drop_column("assets", "family_id")

    op.drop_index("ix_reels_org_id", table_name="reels")
    op.drop_table("reels")

    op.drop_index("ix_asset_families_org_id", table_name="asset_families")
    op.drop_table("asset_families")
