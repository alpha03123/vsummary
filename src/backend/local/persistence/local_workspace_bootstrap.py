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
        workspace_ids = session.execute(
            text(
                "SELECT id FROM workspaces "
                "WHERE owner_scope_id='local-installation' AND deleted_at IS NULL "
                "ORDER BY created_at"
            )
        ).scalars().all()
        if len(workspace_ids) > 1:
            raise RuntimeError("Multiple local-installation Workspaces exist; Local startup cannot choose one.")
        if workspace_ids:
            return str(workspace_ids[0])
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
