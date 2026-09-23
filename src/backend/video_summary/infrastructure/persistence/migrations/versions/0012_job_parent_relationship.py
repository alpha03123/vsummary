"""Persist durable Job parent-child relationships.

Revision ID: 0012_job_parent_relationship
Revises: 0011_outbox_claim_token
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_job_parent_relationship"
down_revision = "0011_outbox_claim_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("parent_job_id", sa.String(length=26), nullable=True))
    op.create_index("ix_jobs_parent_job_id", "jobs", ["parent_job_id"])
    op.create_foreign_key("fk_jobs_parent_job", "jobs", "jobs", ["parent_job_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("fk_jobs_parent_job", "jobs", type_="foreignkey")
    op.drop_index("ix_jobs_parent_job_id", table_name="jobs")
    op.drop_column("jobs", "parent_job_id")
