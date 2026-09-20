"""Scope Agent sessions by Workspace.

Revision ID: 0010_workspace_scoped_agent_sessions
Revises: 0009_job_execution
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa


revision = "0010_workspace_scoped_agent_sessions"
down_revision = "0009_job_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_session_snapshots", sa.Column("workspace_id", sa.String(length=26), nullable=True))
    if not context.is_offline_mode():
        bind = op.get_bind()
        session_count = bind.execute(sa.text("SELECT COUNT(*) FROM agent_session_snapshots")).scalar_one()
        local_workspaces = bind.execute(
            sa.text("SELECT id FROM workspaces WHERE owner_scope_id='local-installation' AND deleted_at IS NULL")
        ).scalars().all()
        if session_count and len(local_workspaces) != 1:
            raise RuntimeError(
                "Cannot migrate Agent sessions without exactly one local-installation Workspace. "
                "Assign sessions to a Workspace explicitly before upgrading."
            )
        if session_count:
            bind.execute(
                sa.text("UPDATE agent_session_snapshots SET workspace_id=:workspace WHERE workspace_id IS NULL"),
                {"workspace": local_workspaces[0]},
            )
    op.alter_column("agent_session_snapshots", "workspace_id", existing_type=sa.String(length=26), nullable=False)
    op.drop_constraint(None, "agent_session_snapshots", type_="primary")
    op.create_primary_key("pk_agent_session_snapshots", "agent_session_snapshots", ["workspace_id", "session_id"])
    op.create_foreign_key(
        "fk_agent_session_snapshots_workspace",
        "agent_session_snapshots",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_session_snapshots_workspace", "agent_session_snapshots", type_="foreignkey")
    op.drop_constraint("pk_agent_session_snapshots", "agent_session_snapshots", type_="primary")
    op.create_primary_key("pk_agent_session_snapshots_legacy", "agent_session_snapshots", ["session_id"])
    op.drop_column("agent_session_snapshots", "workspace_id")
