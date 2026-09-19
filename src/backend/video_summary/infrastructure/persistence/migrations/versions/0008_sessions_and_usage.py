"""Store agent sessions and LLM usage in MySQL.

Revision ID: 0008_sessions_and_usage
Revises: 0007_linked_series
Create Date: 2026-09-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_sessions_and_usage"
down_revision = "0007_linked_series"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("agent_session_snapshots", sa.Column("session_id", sa.String(255), nullable=False), sa.Column("memory_key", sa.String(255), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.PrimaryKeyConstraint("session_id"))
    op.create_table("llm_usage", sa.Column("id", sa.String(26), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("category", sa.String(32), nullable=False), sa.Column("provider", sa.String(128), nullable=False), sa.Column("base_url", sa.String(2048), nullable=False), sa.Column("model", sa.String(512), nullable=False), sa.Column("prompt_tokens", sa.Integer(), nullable=False), sa.Column("completion_tokens", sa.Integer(), nullable=False), sa.Column("total_tokens", sa.Integer(), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_llm_usage_created", "llm_usage", ["created_at"])

def downgrade() -> None:
    op.drop_index("ix_llm_usage_created", table_name="llm_usage"); op.drop_table("llm_usage"); op.drop_table("agent_session_snapshots")
