"""Promote the legacy browser Bilibili inbox to a special series.

Revision ID: 0017_bilibili_inbox_series
Revises: 0016_model_job_resource_id
Create Date: 2026-09-25
"""

from __future__ import annotations

from alembic import op


revision = "0017_bilibili_inbox_series"
down_revision = "0016_model_job_resource_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only migrate an unambiguous legacy inbox. Other linked series remain ordinary series.
    op.execute("""
        UPDATE series AS legacy
        JOIN (
            SELECT workspace_id, MIN(id) AS id
            FROM series
            WHERE source_kind = 'linked'
              AND title = 'B站导入'
              AND deleted_at IS NULL
            GROUP BY workspace_id
            HAVING COUNT(*) = 1
        ) AS candidate ON candidate.id = legacy.id
        LEFT JOIN series AS inbox
          ON inbox.workspace_id = legacy.workspace_id
         AND inbox.source_kind = 'bilibili_inbox'
         AND inbox.deleted_at IS NULL
        SET legacy.source_kind = 'bilibili_inbox', legacy.updated_at = NOW()
        WHERE inbox.id IS NULL
    """)


def downgrade() -> None:
    op.execute("UPDATE series SET source_kind = 'linked', updated_at = NOW() WHERE source_kind = 'bilibili_inbox'")
