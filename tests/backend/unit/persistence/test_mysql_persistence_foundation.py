from __future__ import annotations

import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from backend.video_summary.infrastructure.persistence.database import DatabaseDriverError, DatabaseOptions, _require_pymysql
from backend.video_summary.infrastructure.persistence.migrate import build_alembic_config
from backend.video_summary.infrastructure.persistence.managed_local_mysql import (
    LOCAL_DATABASE_NAME,
    LOCAL_DATABASE_USER,
    ManagedLocalMySql,
    ManagedLocalMySqlError,
    ManagedLocalMySqlPaths,
)
from backend.video_summary.infrastructure.persistence.ids import new_ulid
from backend.video_summary.infrastructure.persistence.models import Base, Job, Video
from backend.video_summary.infrastructure.persistence.sql_video_workspace import _persisted_card_ids
from backend.video_summary.library.models import KnowledgeCardDTO


MYSQL_URL = "mysql+pymysql://vsummary:local-secret@127.0.0.1:3307/vsummary"


class DatabaseOptionsTests(unittest.TestCase):
    def test_accepts_explicit_pymysql_url(self) -> None:
        options = DatabaseOptions(url=MYSQL_URL, pool_size=3, max_overflow=2)

        self.assertEqual(options.parsed_url.drivername, "mysql+pymysql")
        self.assertEqual(options.parsed_url.host, "127.0.0.1")
        self.assertEqual(options.parsed_url.database, "vsummary")

    def test_rejects_non_mysql_database_urls(self) -> None:
        with self.assertRaisesRegex(ValueError, r"mysql\+pymysql"):
            DatabaseOptions(url="sqlite+pysqlite:///vsummary.db")

    def test_rejects_missing_mysql_credentials_or_database(self) -> None:
        with self.assertRaisesRegex(ValueError, "username"):
            DatabaseOptions(url="mysql+pymysql://127.0.0.1:3307/vsummary")
        with self.assertRaisesRegex(ValueError, "password"):
            DatabaseOptions(url="mysql+pymysql://vsummary@127.0.0.1:3307/vsummary")
        with self.assertRaisesRegex(ValueError, "database name"):
            DatabaseOptions(url="mysql+pymysql://vsummary:secret@127.0.0.1")

    def test_missing_driver_has_a_direct_actionable_error(self) -> None:
        from unittest.mock import patch

        with patch("backend.video_summary.infrastructure.persistence.database.importlib.import_module", side_effect=ModuleNotFoundError):
            with self.assertRaisesRegex(DatabaseDriverError, "PyMySQL"):
                _require_pymysql()


class ControlPlaneSchemaTests(unittest.TestCase):
    def test_control_plane_metadata_contains_expected_tables(self) -> None:
        self.assertTrue(
            {
                "app_installations",
                "workspaces",
                "series",
                "videos",
                "media_objects",
                "artifacts",
                "video_content_state",
                "transcripts",
                "transcript_segments",
                "summaries",
                "summary_chapters",
                "job_content_staging",
                "jobs",
                "job_attempts",
                "idempotency_keys",
                "job_events",
                "outbox_events",
            }.issubset(Base.metadata.tables)
        )

    def test_job_active_key_and_video_source_identity_are_unique(self) -> None:
        job_constraint_names = {constraint.name for constraint in Job.__table__.constraints}
        video_constraint_names = {constraint.name for constraint in Video.__table__.constraints}

        self.assertIn("uq_jobs_active_key", job_constraint_names)
        self.assertIn("uq_videos_series_external_source", video_constraint_names)

    def test_schema_compiles_for_mysql(self) -> None:
        ddl = str(CreateTable(Job.__table__).compile(dialect=mysql.dialect()))

        self.assertIn("CREATE TABLE jobs", ddl)
        self.assertIn("CONSTRAINT uq_jobs_active_key UNIQUE (active_key)", ddl)
        self.assertIn("request_payload JSON", ddl)


class AlembicConfigurationTests(unittest.TestCase):
    def test_package_migration_directory_exposes_control_plane_revision(self) -> None:
        config = build_alembic_config(DatabaseOptions(url=MYSQL_URL))
        script = ScriptDirectory.from_config(config)

        self.assertEqual(script.get_current_head(), "0009_job_execution")

    def test_initial_migration_renders_mysql_ddl_without_a_running_server(self) -> None:
        config = build_alembic_config(DatabaseOptions(url=MYSQL_URL))
        output = StringIO()
        config.output_buffer = output

        command.upgrade(config, "head", sql=True)

        ddl = output.getvalue()
        self.assertIn("CREATE TABLE workspaces", ddl)
        self.assertIn("CREATE TABLE jobs", ddl)
        self.assertIn("CREATE TABLE outbox_events", ddl)
        self.assertIn("DEFAULT CURRENT_TIMESTAMP", ddl)
        self.assertNotIn("CURRENT_TIMESTAMP(6)", ddl)


class ManagedLocalMySqlTests(unittest.TestCase):
    def test_data_paths_are_separate_from_the_installation_directory(self) -> None:
        paths = ManagedLocalMySqlPaths(Path("C:/Users/example/AppData/Local/VSummary"))

        self.assertEqual(paths.data_dir, paths.root / "mysql" / "data")
        self.assertEqual(paths.credential_path, paths.root / "mysql" / "vsummary_app.dpapi")
        self.assertEqual(paths.runtime_state_path, paths.root / "mysql" / "runtime.json")

    def test_missing_packaged_runtime_fails_before_creating_user_data(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = ManagedLocalMySql(mysql_home=root / "missing-runtime", data_root=root / "user-data")

            with self.assertRaisesRegex(ManagedLocalMySqlError, "runtime is missing"):
                runtime.start_and_migrate()

            self.assertFalse((root / "user-data").exists())

    def test_bootstrap_sql_creates_only_loopback_application_user(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mysql_home = root / "mysql-runtime"
            (mysql_home / "bin").mkdir(parents=True)
            (mysql_home / "bin" / "mysqld.exe").write_text("stub", encoding="utf-8")
            runtime = ManagedLocalMySql(mysql_home=mysql_home, data_root=root / "user-data")
            runtime._ensure_directories()

            runtime._write_bootstrap_sql("safe-password")

            sql = runtime.paths.bootstrap_sql_path.read_text(encoding="utf-8")
            self.assertIn(f"CREATE DATABASE IF NOT EXISTS {LOCAL_DATABASE_NAME}", sql)
            self.assertIn(f"'{LOCAL_DATABASE_USER}'@'127.0.0.1'", sql)
            self.assertIn("GRANT SHUTDOWN ON *.*", sql)
            self.assertNotIn("'%'", sql)
            self.assertNotIn("ALTER USER 'root'", sql)

    def test_missing_runtime_state_is_rebuilt_from_existing_credentials(self) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mysql_home = root / "mysql-runtime"
            (mysql_home / "bin").mkdir(parents=True)
            (mysql_home / "bin" / "mysqld.exe").write_text("stub", encoding="utf-8")
            runtime = ManagedLocalMySql(mysql_home=mysql_home, data_root=root / "user-data")
            runtime._ensure_directories()
            (runtime.paths.data_dir / "auto.cnf").write_text("[auto]", encoding="utf-8")

            with (
                patch("backend.video_summary.infrastructure.persistence.managed_local_mysql.load_local_mysql_password", return_value="secret"),
                patch("backend.video_summary.infrastructure.persistence.managed_local_mysql._select_loopback_port", return_value=25331),
            ):
                options = runtime._recover_runtime_state()

            self.assertEqual(options.parsed_url.port, 25331)
            self.assertEqual(options.parsed_url.password, "secret")
            self.assertTrue(runtime.paths.runtime_state_path.is_file())


class IdentifierTests(unittest.TestCase):
    def test_ulid_is_fixed_width_and_uses_crockford_alphabet(self) -> None:
        identifier = new_ulid()

        self.assertEqual(len(identifier), 26)
        self.assertRegex(identifier, r"^[0-9ABCDEFGHJKMNPQRSTVWXYZ]{26}$")


class KnowledgeCardPersistenceTests(unittest.TestCase):
    def test_model_card_ids_become_unique_database_ids(self) -> None:
        cards = [
            KnowledgeCardDTO(id="kc-1", title="A", kind="concept", summary="A", details="A", tags=[], keywords=[], related_card_ids=[]),
            KnowledgeCardDTO(id="kc-2", title="B", kind="concept", summary="B", details="B", tags=[], keywords=[], related_card_ids=["kc-1"]),
        ]

        persisted = _persisted_card_ids(cards)

        self.assertEqual(set(persisted), {"kc-1", "kc-2"})
        self.assertNotEqual(persisted["kc-1"], "kc-1")
        self.assertNotEqual(persisted["kc-1"], persisted["kc-2"])
