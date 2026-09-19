"""Create media and artifact metadata tables.

Revision ID: 0002_blob_metadata
Revises: 0001_control_plane
Create Date: 2026-09-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_blob_metadata"
down_revision = "0001_control_plane"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]


def upgrade() -> None:
    op.create_table(
        "media_objects",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("video_id", sa.String(length=26), nullable=False),
        sa.Column("blob_key", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blob_key", name="uq_media_objects_blob_key"),
    )
    op.create_index("ix_media_objects_video_id", "media_objects", ["video_id"])
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("workspace_id", sa.String(length=26), nullable=False),
        sa.Column("video_id", sa.String(length=26), nullable=True),
        sa.Column("series_id", sa.String(length=26), nullable=True),
        sa.Column("content_version", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("blob_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blob_key", name="uq_artifacts_blob_key"),
    )
    op.create_index("ix_artifacts_video_kind", "artifacts", ["video_id", "kind"])
    op.create_index("ix_artifacts_series_kind", "artifacts", ["series_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_series_kind", table_name="artifacts")
    op.drop_index("ix_artifacts_video_kind", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_media_objects_video_id", table_name="media_objects")
    op.drop_table("media_objects")
