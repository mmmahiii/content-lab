"""asset pack review statuses

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_asset_packs_status",
        "asset_packs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_asset_packs_status",
        "asset_packs",
        "status IN ('draft', 'planned', 'approved', 'rejected', 'generating', "
        "'ready', 'failed', 'archived')",
    )


def downgrade() -> None:
    op.execute("UPDATE asset_packs SET status = 'planned' WHERE status IN ('approved', 'rejected')")
    op.drop_constraint(
        "ck_asset_packs_status",
        "asset_packs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_asset_packs_status",
        "asset_packs",
        "status IN ('draft', 'planned', 'generating', 'ready', 'failed', 'archived')",
    )
