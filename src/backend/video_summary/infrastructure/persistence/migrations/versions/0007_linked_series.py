"""Store external linked-series metadata in SQL.

Revision ID: 0007_linked_series
Revises: 0006_rag_chunks
Create Date: 2026-09-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_linked_series"
down_revision = "0006_rag_chunks"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("linked_series_metadata", sa.Column("series_id", sa.String(26), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")), sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("series_id"))

def downgrade() -> None:
    op.drop_table("linked_series_metadata")
