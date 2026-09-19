"""Persist RAG source chunks and index state in MySQL.

Revision ID: 0006_rag_chunks
Revises: 0005_structured_artifacts
Create Date: 2026-09-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_rag_chunks"
down_revision = "0005_structured_artifacts"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("rag_documents", sa.Column("id", sa.String(26), nullable=False), sa.Column("workspace_id", sa.String(26), nullable=False), sa.Column("series_id", sa.String(26), nullable=False), sa.Column("video_id", sa.String(26), nullable=True), sa.Column("source_content_version", sa.Integer(), nullable=False), sa.Column("source_type", sa.String(64), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("state", sa.String(32), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")), sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("video_id", "source_type", name="uq_rag_documents_video_source"))
    op.create_table("rag_chunks", sa.Column("id", sa.String(26), nullable=False), sa.Column("document_id", sa.String(26), nullable=False), sa.Column("source_content_version", sa.Integer(), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("text", sa.Text(), nullable=False), sa.Column("text_hash", sa.String(64), nullable=False), sa.Column("start_ms", sa.Integer(), nullable=True), sa.Column("end_ms", sa.Integer(), nullable=True), sa.Column("chapter_id", sa.String(26), nullable=True), sa.Column("note_id", sa.String(26), nullable=True), sa.Column("card_id", sa.String(26), nullable=True), sa.Column("metadata", sa.JSON(), nullable=False), sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("document_id", "ordinal", name="uq_rag_chunks_document_ordinal"))
    op.create_index("ix_rag_chunks_document", "rag_chunks", ["document_id"])
    op.create_table("rag_index_versions", sa.Column("id", sa.String(26), nullable=False), sa.Column("workspace_id", sa.String(26), nullable=False), sa.Column("embedding_model", sa.String(512), nullable=False), sa.Column("chunker_version", sa.String(64), nullable=False), sa.Column("vector_backend", sa.String(64), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("built_at", sa.DateTime(timezone=True), nullable=True), sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("workspace_id", "embedding_model", "chunker_version", "vector_backend", name="uq_rag_index_version"))
    op.create_table("rag_index_entries", sa.Column("index_version_id", sa.String(26), nullable=False), sa.Column("chunk_id", sa.String(26), nullable=False), sa.Column("vector_document_id", sa.String(255), nullable=True), sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("state", sa.String(32), nullable=False), sa.Column("last_error", sa.Text(), nullable=True), sa.ForeignKeyConstraint(["index_version_id"], ["rag_index_versions.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["chunk_id"], ["rag_chunks.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("index_version_id", "chunk_id"))

def downgrade() -> None:
    op.drop_table("rag_index_entries"); op.drop_table("rag_index_versions"); op.drop_index("ix_rag_chunks_document", table_name="rag_chunks"); op.drop_table("rag_chunks"); op.drop_table("rag_documents")
