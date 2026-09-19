from __future__ import annotations

import asyncio
import argparse
import sys
import os
from pathlib import Path

import uvicorn

from backend.api.di.bootstrap import build_api_container
from backend.api.http.app import create_app


def configure_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy is None:
        return
    asyncio.set_event_loop_policy(selector_policy())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--managed-mysql-home",
        type=Path,
        default=None,
        help="Packaged MySQL runtime directory. Starts and migrates MySQL before serving the API.",
    )
    parser.add_argument(
        "--managed-data-root",
        type=Path,
        default=None,
        help="Managed data root. Defaults to %LOCALAPPDATA%\\VSummary.",
    )
    parser.add_argument(
        "--skip-legacy-import",
        action="store_true",
        help="Skip the one-time legacy workspace importer. Intended for isolated E2E environments.",
    )
    args = parser.parse_args()

    configure_event_loop_policy()
    managed_mysql = None
    application = None
    try:
        if args.managed_mysql_home is not None:
            from backend.video_summary.infrastructure.persistence.managed_local_mysql import ManagedLocalMySql
            from backend.video_summary.infrastructure.persistence.blob_store import FileBlobStore
            from backend.video_summary.infrastructure.persistence.database import create_session_factory
            from backend.video_summary.infrastructure.persistence.legacy_workspace_importer import LegacyWorkspaceImporter
            from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace

            managed_mysql = ManagedLocalMySql(mysql_home=args.managed_mysql_home, data_root=args.managed_data_root)
            database_options = managed_mysql.start_and_migrate()
            data_root = managed_mysql.paths.root
            blob_store = FileBlobStore(data_root / "blobs")
            sessions = create_session_factory(database_options)
            _ensure_local_workspace(sessions)
            if not args.skip_legacy_import:
                LegacyWorkspaceImporter(root_dir=_repository_root(), session_factory=sessions, blob_store=blob_store).import_local_workspace()
            workspace = SqlVideoWorkspace(session_factory=sessions, blob_store=blob_store, cache_root=data_root / "cache")
            application = create_app(container=build_api_container(_repository_root(), workspace_override=workspace))
        if application is None:
            application = create_app()
        uvicorn.run(application, host=args.host, port=args.port)
    finally:
        if managed_mysql is not None:
            managed_mysql.stop()


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _ensure_local_workspace(session_factory) -> None:
    """Create the single local-installation workspace before any import or API request."""

    from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace
    from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository

    # Local mode intentionally has one owner scope. Cloud hosts provide their
    # own workspace provisioning and do not use this managed-local entrypoint.
    workspace = SqlVideoWorkspace.get_workspace_id(session_factory)
    if workspace is None:
        SqlControlPlaneRepository(session_factory).create_workspace(
            owner_scope_id="local-installation",
            title="VSummary",
        )


if __name__ == "__main__":
    main()
