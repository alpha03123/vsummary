"""Track idempotent legacy workspace imports.

Revision ID: 0004_legacy_import_tracking
Revises: 0003_current_content_staging
Create Date: 2026-09-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_legacy_import_tracking"
down_revision = "0003_current_content_staging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legacy_import_items",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_key", sa.String(length=512), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=26), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_kind", "source_key", name="uq_legacy_import_source"),
    )


def downgrade() -> None:
    op.drop_table("legacy_import_items")
