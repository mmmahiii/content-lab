"""widen asset_key storage and rely on asset_key_hash uniqueness

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_assets_org_asset_key", table_name="assets")
    op.alter_column(
        "assets",
        "asset_key",
        existing_type=sa.String(length=512),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "assets",
        "asset_key",
        existing_type=sa.Text(),
        type_=sa.String(length=512),
        existing_nullable=True,
        postgresql_using="left(asset_key, 512)",
    )
    op.create_index(
        "uq_assets_org_asset_key",
        "assets",
        ["org_id", "asset_key"],
        unique=True,
        postgresql_where=sa.text("asset_key IS NOT NULL"),
    )
