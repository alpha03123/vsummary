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
    # Early revisions used Alembic's legacy VARCHAR(32) version column, while
    # this revision identifier is longer. Expand it before Alembic records the
    # completed revision, otherwise a successfully applied schema change would
    # fail only when writing ``alembic_version``.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        nullable=False,
    )
    if context.is_offline_mode():
        op.add_column("agent_session_snapshots", sa.Column("workspace_id", sa.String(length=26), nullable=True))
    else:
        bind = op.get_bind()
        has_workspace_id = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema=DATABASE() "
                "AND table_name='agent_session_snapshots' "
                "AND column_name='workspace_id'"
            )
        ).scalar_one()
        if not has_workspace_id:
            op.add_column("agent_session_snapshots", sa.Column("workspace_id", sa.String(length=26), nullable=True))
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
    if context.is_offline_mode():
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
        return
    primary_key_columns = bind.execute(
        sa.text(
            "SELECT column_name FROM information_schema.key_column_usage "
            "WHERE table_schema=DATABASE() "
            "AND table_name='agent_session_snapshots' "
            "AND constraint_name='PRIMARY' ORDER BY ordinal_position"
        )
    ).scalars().all()
    if primary_key_columns != ["workspace_id", "session_id"]:
        if primary_key_columns:
            op.drop_constraint(None, "agent_session_snapshots", type_="primary")
        op.create_primary_key("pk_agent_session_snapshots", "agent_session_snapshots", ["workspace_id", "session_id"])
    foreign_key_exists = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.key_column_usage "
            "WHERE table_schema=DATABASE() "
            "AND table_name='agent_session_snapshots' "
            "AND column_name='workspace_id' "
            "AND referenced_table_name='workspaces'"
        )
    ).scalar_one()
    if not foreign_key_exists:
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
