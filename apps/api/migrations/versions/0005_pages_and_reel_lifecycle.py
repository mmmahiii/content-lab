"""pages and reel lifecycle tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False, server_default="owned"),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("external_page_id", sa.String(256), nullable=True),
        sa.Column("handle", sa.String(256), nullable=True),
        sa.Column("display_name", sa.String(512), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
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
        sa.CheckConstraint("kind IN ('owned', 'competitor')", name="ck_pages_kind"),
    )
    op.create_index("ix_pages_org_id", "pages", ["org_id"])
    op.create_index("ix_pages_org_id_kind", "pages", ["org_id", "kind"])
    op.create_index("ix_pages_org_id_created_at", "pages", ["org_id", "created_at"])
    op.create_index(
        "uq_pages_org_platform_external_page_id",
        "pages",
        ["org_id", "platform", "external_page_id"],
        unique=True,
        postgresql_where=sa.text("external_page_id IS NOT NULL"),
    )

    op.create_table(
        "reel_families",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
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
    )
    op.create_index("ix_reel_families_org_id", "reel_families", ["org_id"])
    op.create_index("ix_reel_families_page_id", "reel_families", ["page_id"])
    op.create_index(
        "ix_reel_families_org_id_page_id",
        "reel_families",
        ["org_id", "page_id"],
    )

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
            "reel_family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reel_families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("origin", sa.String(32), nullable=False, server_default="generated"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("variant_label", sa.String(64), nullable=True),
        sa.Column("external_reel_id", sa.String(256), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
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
        sa.CheckConstraint("origin IN ('generated', 'observed')", name="ck_reels_origin"),
        sa.CheckConstraint(
            "(origin = 'generated' AND status IN ("
            "'draft', 'planning', 'generating', 'editing', 'qa', "
            "'qa_failed', 'ready', 'posted', 'archived'"
            ")) OR (origin = 'observed' AND status IN ('active', 'removed', 'unavailable'))",
            name="ck_reels_origin_status",
        ),
    )
    op.create_index("ix_reels_org_id", "reels", ["org_id"])
    op.create_index("ix_reels_reel_family_id", "reels", ["reel_family_id"])
    op.create_index(
        "ix_reels_org_id_reel_family_id",
        "reels",
        ["org_id", "reel_family_id"],
    )
    op.create_index(
        "ix_reels_org_id_origin_status",
        "reels",
        ["org_id", "origin", "status"],
    )
    op.create_index(
        "uq_reels_org_external_reel_id_observed",
        "reels",
        ["org_id", "external_reel_id"],
        unique=True,
        postgresql_where=sa.text("origin = 'observed' AND external_reel_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_reels_org_external_reel_id_observed", table_name="reels")
    op.drop_index("ix_reels_org_id_origin_status", table_name="reels")
    op.drop_index("ix_reels_org_id_reel_family_id", table_name="reels")
    op.drop_index("ix_reels_reel_family_id", table_name="reels")
    op.drop_index("ix_reels_org_id", table_name="reels")
    op.drop_table("reels")

    op.drop_index("ix_reel_families_org_id_page_id", table_name="reel_families")
    op.drop_index("ix_reel_families_page_id", table_name="reel_families")
    op.drop_index("ix_reel_families_org_id", table_name="reel_families")
    op.drop_table("reel_families")

    op.drop_index("uq_pages_org_platform_external_page_id", table_name="pages")
    op.drop_index("ix_pages_org_id_created_at", table_name="pages")
    op.drop_index("ix_pages_org_id_kind", table_name="pages")
    op.drop_index("ix_pages_org_id", table_name="pages")
    op.drop_table("pages")
