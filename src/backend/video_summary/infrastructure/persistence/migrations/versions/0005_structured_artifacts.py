"""Store notes, cards, mindmaps, AI summaries and catalogs in SQL.

Revision ID: 0005_structured_artifacts
Revises: 0004_legacy_import_tracking
Create Date: 2026-09-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_structured_artifacts"
down_revision = "0004_legacy_import_tracking"
branch_labels = None
depends_on = None

def _timestamps() -> list[sa.Column[object]]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))]

def upgrade() -> None:
    op.create_table("notes", sa.Column("id", sa.String(26), nullable=False), sa.Column("video_id", sa.String(26), nullable=False), sa.Column("title", sa.String(1024), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("source", sa.String(32), nullable=False), sa.Column("row_version", sa.Integer(), nullable=False), sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True), *_timestamps(), sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_notes_video_updated", "notes", ["video_id", "updated_at"])
    op.create_table("ai_summaries", sa.Column("video_id", sa.String(26), nullable=False), sa.Column("title", sa.String(1024), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("citations", sa.JSON(), nullable=False), sa.Column("status", sa.String(32), nullable=False), *_timestamps(), sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("video_id"))
    op.create_table("ai_summary_visual_evidence", sa.Column("id", sa.String(26), nullable=False), sa.Column("video_id", sa.String(26), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("timestamp_ms", sa.Integer(), nullable=False), sa.Column("text", sa.Text(), nullable=False), sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("video_id", "ordinal", name="uq_ai_summary_evidence_ordinal"))
    op.create_table("knowledge_card_sets", sa.Column("video_id", sa.String(26), nullable=False), sa.Column("content_version", sa.Integer(), nullable=False), sa.Column("title", sa.String(1024), nullable=False), sa.Column("status", sa.String(32), nullable=False), *_timestamps(), sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("video_id"))
    op.create_table("knowledge_cards", sa.Column("id", sa.String(26), nullable=False), sa.Column("video_id", sa.String(26), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("title", sa.String(1024), nullable=False), sa.Column("kind", sa.String(64), nullable=False), sa.Column("summary", sa.Text(), nullable=False), sa.Column("details", sa.Text(), nullable=False), sa.Column("tags", sa.JSON(), nullable=False), sa.Column("keywords", sa.JSON(), nullable=False), sa.Column("related_card_ids", sa.JSON(), nullable=False), sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("video_id", "ordinal", name="uq_knowledge_cards_video_ordinal"))
    op.create_table("mindmaps", sa.Column("id", sa.String(26), nullable=False), sa.Column("video_id", sa.String(26), nullable=True), sa.Column("series_id", sa.String(26), nullable=True), sa.Column("content_version", sa.Integer(), nullable=True), sa.Column("title", sa.String(1024), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("row_version", sa.Integer(), nullable=False), *_timestamps(), sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("video_id", name="uq_mindmaps_video"), sa.UniqueConstraint("series_id", name="uq_mindmaps_series"))
    op.create_table("series_catalogs", sa.Column("series_id", sa.String(26), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), *_timestamps(), sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("series_id"))

def downgrade() -> None:
    op.drop_table("series_catalogs"); op.drop_table("mindmaps"); op.drop_table("knowledge_cards"); op.drop_table("knowledge_card_sets"); op.drop_table("ai_summary_visual_evidence"); op.drop_table("ai_summaries"); op.drop_index("ix_notes_video_updated", table_name="notes"); op.drop_table("notes")
