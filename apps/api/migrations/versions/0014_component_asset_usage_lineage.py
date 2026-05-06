"""component asset usage lineage

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "planned_asset_specs",
        sa.Column(
            "compatibility_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "asset_pack_items",
        sa.Column(
            "compatibility_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("asset_usage", sa.Column("component_role", sa.String(64), nullable=True))
    op.add_column("asset_usage", sa.Column("layer_role", sa.String(64), nullable=True))
    op.add_column("asset_usage", sa.Column("sequence_index", sa.Integer(), nullable=True))
    op.add_column("asset_usage", sa.Column("z_index", sa.Integer(), nullable=True))
    op.add_column("asset_usage", sa.Column("start_time", sa.Float(), nullable=True))
    op.add_column("asset_usage", sa.Column("end_time", sa.Float(), nullable=True))
    op.add_column("asset_usage", sa.Column("transform_recipe", postgresql.JSONB(), nullable=True))
    op.add_column("asset_usage", sa.Column("transform_version", sa.String(64), nullable=True))
    op.add_column(
        "asset_usage",
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute("UPDATE asset_usage SET component_role = usage_role WHERE component_role IS NULL")
    op.create_index("ix_asset_usage_component_role", "asset_usage", ["component_role"])


def downgrade() -> None:
    op.drop_index("ix_asset_usage_component_role", table_name="asset_usage")
    op.drop_column("asset_usage", "metadata_json")
    op.drop_column("asset_usage", "transform_version")
    op.drop_column("asset_usage", "transform_recipe")
    op.drop_column("asset_usage", "end_time")
    op.drop_column("asset_usage", "start_time")
    op.drop_column("asset_usage", "z_index")
    op.drop_column("asset_usage", "sequence_index")
    op.drop_column("asset_usage", "layer_role")
    op.drop_column("asset_usage", "component_role")
    op.drop_column("asset_pack_items", "compatibility_metadata")
    op.drop_column("planned_asset_specs", "compatibility_metadata")
