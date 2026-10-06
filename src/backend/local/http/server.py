"""Local server entry point and managed-MySQL composition."""

from __future__ import annotations

import argparse
import asyncio
import sys
from contextlib import contextmanager
from pathlib import Path

import uvicorn

from backend.local.composition import build_local_container
from backend.local.http.app import create_app
from backend.local.persistence.managed_mysql import ManagedLocalMySqlPathError


def configure_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy is not None:
        asyncio.set_event_loop_policy(selector_policy())


def _exit_for_mysql_path_error(error: Exception) -> None:
    raise SystemExit(f"启动失败：{error}") from None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--managed-mysql-home", type=Path, default=None)
    parser.add_argument("--managed-data-root", type=Path, default=None)
    parser.add_argument("--runtime-root", type=Path, help="Directory containing .env, config/settings.toml and runtime caches.")
    args = parser.parse_args()

    configure_event_loop_policy()
    if args.managed_mysql_home is None:
        raise RuntimeError("Local server requires --managed-mysql-home.")

    try:
        with local_server(
            mysql_home=args.managed_mysql_home,
            data_root=args.managed_data_root,
            runtime_root=args.runtime_root,
            host=args.host,
            port=args.port,
        ) as server:
            server.run()
    except ManagedLocalMySqlPathError as error:
        _exit_for_mysql_path_error(error)


@contextmanager
def local_server(*, mysql_home: Path, data_root: Path | None = None,
                 runtime_root: Path | None = None, host: str = "127.0.0.1", port: int = 8001):
    """Own the Local runtime lifecycle shared by the CLI and E2E runners."""
    repository_root = _repository_root()
    root_dir = repository_root
    if runtime_root is not None:
        root_dir = runtime_root.resolve(strict=True)
        if not (root_dir / "config/settings.toml").is_file():
            raise FileNotFoundError(f"Runtime settings are missing: {root_dir / 'config/settings.toml'}")
        if data_root is None:
            data_root = root_dir / "data/local"

    from backend.video_summary.infrastructure.persistence.file_blob_store import FileBlobStore
    from backend.local.persistence.local_workspace_bootstrap import ensure_local_workspace_before_migration
    from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
    from backend.video_summary.infrastructure.persistence.database import create_session_factory
    from backend.local.persistence.managed_mysql import ManagedLocalMySql
    from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace

    managed_mysql = ManagedLocalMySql(mysql_home=mysql_home, data_root=data_root)
    sessions = None
    try:
        database_options = managed_mysql.start_and_migrate(
            before_migrate=lambda options: ensure_local_workspace_before_migration(
                create_session_factory(options)
            )
        )
        data_root = managed_mysql.paths.root
        sessions = create_session_factory(database_options)
        workspace_id = SqlVideoWorkspace.get_local_workspace_id(sessions)
        if workspace_id is None:
            workspace_id = SqlControlPlaneRepository(sessions).create_workspace(
                owner_scope_id="local-installation",
                title="VSummary",
            )
        blob_store = FileBlobStore(data_root / "blobs")
        workspace = SqlVideoWorkspace(
            session_factory=sessions,
            blob_store=blob_store,
            cache_root=data_root / "cache",
            workspace_id=workspace_id,
        )
        container = build_local_container(root_dir, workspace=workspace)
        yield uvicorn.Server(uvicorn.Config(create_app(container, frontend_root=repository_root), host=host, port=port))
    finally:
        if sessions is not None:
            sessions.kw["bind"].dispose()
        managed_mysql.stop()


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


if __name__ == "__main__":
    main()
