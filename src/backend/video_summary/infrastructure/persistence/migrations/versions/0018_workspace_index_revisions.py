"""Durable workspace index refresh generations."""

from alembic import op
import sqlalchemy as sa

revision = "0018_workspace_index_revisions"
down_revision = "0017_bilibili_inbox_series"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_jobs_parent_resource_operation",
        "jobs",
        ["parent_job_id", "resource_type", "resource_id", "operation"],
    )
    op.add_column(
        "workspaces", sa.Column("index_generation", sa.String(26), nullable=True)
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "index_revision_requested",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "index_revision_completed",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade():
    op.drop_constraint("uq_jobs_parent_resource_operation", "jobs", type_="unique")
    op.drop_column("workspaces", "index_generation")
    op.drop_column("workspaces", "index_revision_completed")
    op.drop_column("workspaces", "index_revision_requested")
