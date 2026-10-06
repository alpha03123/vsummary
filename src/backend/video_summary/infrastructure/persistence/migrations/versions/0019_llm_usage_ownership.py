"""Attribute LLM usage to its authenticated workspace and actor."""

from alembic import op
import sqlalchemy as sa

revision = "0019_llm_usage_ownership"
down_revision = "0018_workspace_index_revisions"
branch_labels = None
depends_on = None


def upgrade():
    # Historical rows have no reliable owner. Never assign them to a Cloud account.
    op.add_column("llm_usage", sa.Column("workspace_id", sa.String(26), nullable=True))
    op.add_column("llm_usage", sa.Column("actor_id", sa.String(128), nullable=True))
    op.create_index("ix_llm_usage_workspace_actor_created", "llm_usage", ["workspace_id", "actor_id", "created_at"])
    op.create_index("ix_llm_usage_actor_created", "llm_usage", ["actor_id", "created_at"])


def downgrade():
    op.drop_index("ix_llm_usage_actor_created", table_name="llm_usage")
    op.drop_index("ix_llm_usage_workspace_actor_created", table_name="llm_usage")
    op.drop_column("llm_usage", "actor_id")
    op.drop_column("llm_usage", "workspace_id")
