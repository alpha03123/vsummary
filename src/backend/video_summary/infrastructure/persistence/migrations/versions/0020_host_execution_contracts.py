"""Actor-indexed tasks, operation-level token usage and recoverable accounting."""
from alembic import op
import sqlalchemy as sa

revision = "0020_host_execution_contracts"
down_revision = "0019_llm_usage_ownership"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("llm_usage", sa.Column("operation_id", sa.String(128), nullable=True))
    op.create_index("ix_llm_usage_operation", "llm_usage", ["operation_id"])
    op.add_column("jobs", sa.Column("actor_id", sa.String(128), nullable=True))
    op.add_column("jobs", sa.Column("accounting_status", sa.String(32), nullable=False, server_default="none"))
    op.execute("""UPDATE jobs SET actor_id=JSON_UNQUOTE(JSON_EXTRACT(request_payload,'$._execution_context.actor_id'))
        WHERE JSON_EXTRACT(request_payload,'$._execution_context.actor_id') IS NOT NULL""")
    op.execute("""UPDATE jobs SET accounting_status=CASE
        WHEN JSON_EXTRACT(request_payload,'$._quota_reservation.finalized')=true THEN 'settled' ELSE 'pending' END
        WHERE JSON_EXTRACT(request_payload,'$._quota_reservation.id') IS NOT NULL""")
    op.create_index("ix_jobs_actor_created", "jobs", ["workspace_id", "actor_id", "created_at"])
    op.create_index("ix_jobs_accounting", "jobs", ["accounting_status", "status"])
    op.create_table("chat_queue_state", sa.Column("id", sa.String(32), primary_key=True))
    op.create_table("chat_requests",
        sa.Column("sequence", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(128), nullable=False, unique=True),
        sa.Column("workspace_id", sa.String(26), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reservation_id", sa.String(128), nullable=True),
        sa.Column("model_profile", sa.String(64), nullable=True),
        sa.Column("accounting_status", sa.String(32), nullable=False, server_default="none"),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=False))
    op.create_index("ix_chat_requests_queue", "chat_requests", ["status", "created_at"])
    op.create_index("ix_chat_requests_actor", "chat_requests", ["actor_id", "status"])


def downgrade():
    op.drop_table("chat_requests")
    op.drop_table("chat_queue_state")
    op.drop_index("ix_jobs_accounting", table_name="jobs")
    op.drop_index("ix_jobs_actor_created", table_name="jobs")
    op.drop_column("jobs", "accounting_status")
    op.drop_column("jobs", "actor_id")
    op.drop_index("ix_llm_usage_operation", table_name="llm_usage")
    op.drop_column("llm_usage", "operation_id")
