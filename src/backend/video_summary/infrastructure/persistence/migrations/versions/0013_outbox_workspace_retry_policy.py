"""Scope Outbox events and persist bounded retry state.

Revision ID: 0013_outbox_workspace_retry_policy
Revises: 0012_job_parent_relationship
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa


revision = "0013_outbox_workspace_retry_policy"
down_revision = "0012_job_parent_relationship"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _prepare_schema()
    op.execute(
        """
        UPDATE outbox_events AS outbox_event
        LEFT JOIN videos AS content_video
            ON outbox_event.aggregate_type = 'video_content'
            AND content_video.id = outbox_event.aggregate_id
        LEFT JOIN notes AS note
            ON outbox_event.aggregate_type = 'note'
            AND note.id = outbox_event.aggregate_id
        LEFT JOIN videos AS note_video ON note_video.id = note.video_id
        LEFT JOIN jobs AS job
            ON outbox_event.aggregate_type = 'job'
            AND job.id = outbox_event.aggregate_id
        LEFT JOIN series AS series
            ON series.id = COALESCE(content_video.series_id, note_video.series_id)
        SET outbox_event.workspace_id = COALESCE(series.workspace_id, job.workspace_id)
        WHERE outbox_event.workspace_id IS NULL
        """
    )
    if not context.is_offline_mode():
        missing_workspace = op.get_bind().scalar(
            sa.text("SELECT COUNT(*) FROM outbox_events WHERE workspace_id IS NULL")
        )
        if missing_workspace:
            raise RuntimeError(
                "Cannot scope existing Outbox events to a Workspace. Resolve their aggregate references before upgrading."
            )
    _finalize_schema()


def _prepare_schema() -> None:
    if context.is_offline_mode() or _index_exists("ix_outbox_delivery"):
        op.drop_index("ix_outbox_delivery", table_name="outbox_events")
    _add_column_if_missing("workspace_id", sa.Column("workspace_id", sa.String(length=26), nullable=True))
    _add_column_if_missing(
        "available_at",
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    _add_column_if_missing("dead_lettered_at", sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("last_error", sa.Column("last_error", sa.Text(), nullable=True))


def _finalize_schema() -> None:
    if _workspace_id_is_nullable():
        op.alter_column("outbox_events", "workspace_id", existing_type=sa.String(length=26), nullable=False)
    if not _foreign_key_exists("fk_outbox_events_workspace"):
        op.create_foreign_key(
            "fk_outbox_events_workspace",
            "outbox_events",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if context.is_offline_mode() or not _index_exists("ix_outbox_delivery"):
        op.create_index(
            "ix_outbox_delivery",
            "outbox_events",
            ["workspace_id", "delivered_at", "dead_lettered_at", "available_at", "claimed_at", "occurred_at"],
        )


def _add_column_if_missing(name: str, column: sa.Column) -> None:
    if _column_exists(name):
        return
    op.add_column("outbox_events", column)


def _column_exists(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("outbox_events")}


def _workspace_id_is_nullable() -> bool:
    if context.is_offline_mode():
        return True
    columns = {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns("outbox_events")}
    return bool(columns["workspace_id"]["nullable"])


def _index_exists(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("outbox_events")}


def _foreign_key_exists(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in {foreign_key["name"] for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys("outbox_events")}


def downgrade() -> None:
    op.drop_index("ix_outbox_delivery", table_name="outbox_events")
    op.drop_constraint("fk_outbox_events_workspace", "outbox_events", type_="foreignkey")
    op.drop_column("outbox_events", "last_error")
    op.drop_column("outbox_events", "dead_lettered_at")
    op.drop_column("outbox_events", "available_at")
    op.drop_column("outbox_events", "workspace_id")
    op.create_index("ix_outbox_delivery", "outbox_events", ["delivered_at", "claimed_at", "occurred_at"])
