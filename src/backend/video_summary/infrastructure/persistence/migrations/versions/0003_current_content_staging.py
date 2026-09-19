"""Create current content and job staging tables.

Revision ID: 0003_current_content_staging
Revises: 0002_blob_metadata
Create Date: 2026-09-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_current_content_staging"
down_revision = "0002_blob_metadata"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]


def upgrade() -> None:
    op.create_table(
        "video_content_state",
        sa.Column("video_id", sa.String(length=26), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("transcript_version", sa.Integer(), nullable=False),
        sa.Column("summary_version", sa.Integer(), nullable=False),
        sa.Column("cards_version", sa.Integer(), nullable=False),
        sa.Column("mindmap_version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("video_id"),
    )
    op.create_table(
        "transcripts",
        sa.Column("video_id", sa.String(length=26), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("raw_srt_artifact_id", sa.String(length=26), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_srt_artifact_id"], ["artifacts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("video_id"),
    )
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("video_id", sa.String(length=26), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", "content_version", "ordinal", name="uq_transcript_segments_version_ordinal"),
    )
    op.create_index("ix_transcript_segments_video_time", "transcript_segments", ["video_id", "start_ms"])
    op.create_table(
        "summaries",
        sa.Column("video_id", sa.String(length=26), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("content_format_version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("video_id"),
    )
    op.create_table(
        "summary_chapters",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("video_id", sa.String(length=26), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", "content_version", "ordinal", name="uq_summary_chapters_version_ordinal"),
    )
    op.create_table(
        "job_content_staging",
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("video_id", sa.String(length=26), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id"),
    )


def downgrade() -> None:
    op.drop_table("job_content_staging")
    op.drop_table("summary_chapters")
    op.drop_table("summaries")
    op.drop_index("ix_transcript_segments_video_time", table_name="transcript_segments")
    op.drop_table("transcript_segments")
    op.drop_table("transcripts")
    op.drop_table("video_content_state")
