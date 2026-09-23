"""Preserve local series storage modes and external media paths.

Revision ID: 0014_media_storage_modes
Revises: 0013_outbox_workspace_retry_policy
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_media_storage_modes"
down_revision = "0013_outbox_workspace_retry_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "series",
        sa.Column("storage_mode", sa.String(length=32), nullable=False, server_default="copy"),
    )
    op.create_table(
        "external_media_references",
        sa.Column("video_id", sa.String(length=26), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("video_id"),
    )


def downgrade() -> None:
    op.drop_table("external_media_references")
    op.drop_column("series", "storage_mode")
