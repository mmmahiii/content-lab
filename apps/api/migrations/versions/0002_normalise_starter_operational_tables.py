"""normalise starter operational tables for phase-1 naming

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE assets RENAME COLUMN kind TO asset_class")
    op.execute("ALTER TABLE assets RENAME COLUMN storage_key TO storage_uri")

    op.execute("ALTER TABLE runs RENAME COLUMN name TO workflow_key")
    op.execute("ALTER TABLE runs RENAME COLUMN config TO input_params")
    op.execute("ALTER TABLE runs RENAME COLUMN result TO output_payload")

    op.add_column(
        "outbox_events",
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE outbox_events SET dispatched_at = created_at WHERE published IS TRUE")
    op.drop_index("ix_outbox_events_published", table_name="outbox_events")
    op.drop_column("outbox_events", "published")
    op.create_index(
        "ix_outbox_events_undispatched",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("dispatched_at IS NULL"),
    )

    op.execute("ALTER TABLE run_assets RENAME COLUMN role TO asset_role")


def downgrade() -> None:
    op.execute("ALTER TABLE run_assets RENAME COLUMN asset_role TO role")

    op.drop_index("ix_outbox_events_undispatched", table_name="outbox_events")
    op.add_column(
        "outbox_events",
        sa.Column(
            "published",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.execute("UPDATE outbox_events SET published = TRUE WHERE dispatched_at IS NOT NULL")
    op.drop_column("outbox_events", "dispatched_at")
    op.create_index("ix_outbox_events_published", "outbox_events", ["published"])

    op.execute("ALTER TABLE runs RENAME COLUMN output_payload TO result")
    op.execute("ALTER TABLE runs RENAME COLUMN input_params TO config")
    op.execute("ALTER TABLE runs RENAME COLUMN workflow_key TO name")

    op.execute("ALTER TABLE assets RENAME COLUMN storage_uri TO storage_key")
    op.execute("ALTER TABLE assets RENAME COLUMN asset_class TO kind")
