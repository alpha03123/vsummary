"""Local-only workspace bootstrap required before legacy schema upgrades."""

from __future__ import annotations

from sqlalchemy import text

from backend.core.ids import new_ulid


def ensure_local_workspace_before_migration(session_factory) -> str | None:
    """Ensure the legacy Local database has one explicit Workspace.

    Revision 0010 scopes existing Agent sessions by Workspace. A legacy Local
    database already has the ``workspaces`` table but may predate the explicit
    ``local-installation`` record created by the current composition root.
    This runs before Alembic so that revision can safely assign those sessions.
    Empty databases have no table yet and remain Alembic's responsibility.
    """
    with session_factory.begin() as session:
        has_workspaces = session.execute(text("SHOW TABLES LIKE 'workspaces'")).scalar()
        if has_workspaces is None:
            return None
        local_workspace_ids = session.execute(
            text(
                "SELECT id FROM workspaces "
                "WHERE owner_scope_id='local-installation' AND deleted_at IS NULL "
                "ORDER BY created_at"
            )
        ).scalars().all()
        legacy_workspace_ids = session.execute(
            text(
                "SELECT id FROM workspaces "
                "WHERE owner_scope_id='legacy-local' AND deleted_at IS NULL "
                "ORDER BY created_at"
            )
        ).scalars().all()
        if len(local_workspace_ids) > 1:
            raise RuntimeError("Multiple local-installation Workspaces exist; Local startup cannot choose one.")
        if len(legacy_workspace_ids) > 1:
            raise RuntimeError("Multiple legacy-local Workspaces exist; Local startup cannot choose one.")
        if legacy_workspace_ids:
            legacy_workspace_id = str(legacy_workspace_ids[0])
            if not local_workspace_ids:
                _promote_legacy_workspace(session, legacy_workspace_id)
                return legacy_workspace_id
            local_workspace_id = str(local_workspace_ids[0])
            legacy_series_count = _active_series_count(session, legacy_workspace_id)
            local_series_count = _active_series_count(session, local_workspace_id)
            if legacy_series_count and local_series_count:
                raise RuntimeError(
                    "Both local-installation and legacy-local Workspaces contain series; Local startup cannot choose one."
                )
            if legacy_series_count:
                active_job_count = session.execute(
                    text(
                        "SELECT COUNT(*) FROM jobs WHERE workspace_id=:workspace "
                        "AND status IN ('queued','retrying','running','cancelling')"
                    ),
                    {"workspace": local_workspace_id},
                ).scalar_one()
                if active_job_count:
                    raise RuntimeError(
                        "The empty local-installation Workspace has active Jobs; Local startup cannot replace it."
                    )
                session.execute(
                    text("UPDATE workspaces SET deleted_at=NOW(),updated_at=NOW() WHERE id=:workspace"),
                    {"workspace": local_workspace_id},
                )
                _promote_legacy_workspace(session, legacy_workspace_id)
                return legacy_workspace_id
            return local_workspace_id
        if local_workspace_ids:
            return str(local_workspace_ids[0])
        workspace_id = new_ulid()
        session.execute(
            text(
                "INSERT INTO workspaces "
                "(id,owner_scope_id,title,row_version,created_at,updated_at) "
                "VALUES (:id,'local-installation','VSummary',1,NOW(),NOW())"
            ),
            {"id": workspace_id},
        )
        return workspace_id


def _active_series_count(session, workspace_id: str) -> int:
    return int(
        session.execute(
            text("SELECT COUNT(*) FROM series WHERE workspace_id=:workspace AND deleted_at IS NULL"),
            {"workspace": workspace_id},
        ).scalar_one()
    )


def _promote_legacy_workspace(session, workspace_id: str) -> None:
    session.execute(
        text(
            "UPDATE workspaces SET owner_scope_id='local-installation',row_version=row_version+1,updated_at=NOW() "
            "WHERE id=:workspace"
        ),
        {"workspace": workspace_id},
    )
