"""Add ownership token to Outbox leases.

Revision ID: 0011_outbox_claim_token
Revises: 0010_workspace_scoped_agent_sessions
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_outbox_claim_token"
down_revision = "0010_workspace_scoped_agent_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("claim_token", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("outbox_events", "claim_token")
