"""Persist manual legacy migration runs and stage imported series.

Revision ID: 0015_manual_legacy_migration
Revises: 0014_media_storage_modes
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_manual_legacy_migration"
down_revision = "0014_media_storage_modes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legacy_migration_runs",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("source_root", sa.Text(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("include_data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("total_videos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_videos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed_videos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("series", sa.Column("migration_run_id", sa.String(length=26), nullable=True))
    op.add_column("series", sa.Column("import_published", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("series", "import_published")
    op.drop_column("series", "migration_run_id")
    op.drop_table("legacy_migration_runs")
