"""Allow model identifiers in job resource IDs.

Revision ID: 0016_model_job_resource_id
Revises: 0015_manual_legacy_migration
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_model_job_resource_id"
down_revision = "0015_manual_legacy_migration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("jobs", "resource_id", existing_type=sa.String(26), type_=sa.String(128), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("jobs", "resource_id", existing_type=sa.String(128), type_=sa.String(26), existing_nullable=False)
