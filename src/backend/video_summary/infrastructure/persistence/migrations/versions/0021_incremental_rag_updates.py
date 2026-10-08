"""Persist coalesced RAG changes until an index generation is published."""

from alembic import op
import sqlalchemy as sa

revision = "0021_incremental_rag_updates"
down_revision = "0020_host_execution_contracts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workspaces", sa.Column("index_pending_changes", sa.JSON(), nullable=False,
        server_default=sa.text("(JSON_OBJECT())")))
    op.execute("""UPDATE workspaces
        SET index_pending_changes=JSON_OBJECT('workspace', JSON_OBJECT(
            'action', 'refresh_all', 'revision', index_revision_requested))
        WHERE index_revision_requested > index_revision_completed""")


def downgrade():
    op.drop_column("workspaces", "index_pending_changes")
