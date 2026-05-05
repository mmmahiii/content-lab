"""asset pack item provenance statuses

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_asset_pack_items_status",
        "asset_pack_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_asset_pack_items_status",
        "asset_pack_items",
        "status IN ('planned', 'generating', 'generated', 'uploaded', 'imported', "
        "'reused', 'selected', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_asset_pack_items_status",
        "asset_pack_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_asset_pack_items_status",
        "asset_pack_items",
        "status IN ('planned', 'generating', 'generated', 'uploaded', 'selected', 'failed')",
    )
