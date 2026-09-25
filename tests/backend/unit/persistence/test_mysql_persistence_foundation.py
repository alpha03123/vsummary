from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.script import ScriptDirectory

from backend.video_summary.infrastructure.persistence.database import DatabaseDriverError, DatabaseOptions, _require_pymysql
from backend.video_summary.infrastructure.persistence.migrate import build_alembic_config
from backend.local.persistence.managed_mysql import (
    CREDENTIAL_FILE,
    LOCAL_DATABASE_NAME,
    LOCAL_DATABASE_USER,
    ManagedLocalMySql,
    ManagedLocalMySqlError,
    ManagedLocalMySqlPathError,
    ManagedLocalMySqlPaths,
    _default_data_root,
)
from backend.core.ids import new_ulid
from backend.video_summary.infrastructure.persistence.models import Base, Job, OutboxEvent, Series, Video
from backend.video_summary.infrastructure.persistence.sql_video_workspace import _enqueue_outbox_event, _persisted_card_ids
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

    def test_job_resource_id_fits_supported_asr_model_keys(self) -> None:
        from backend.video_summary.infrastructure.asr.whisper_cpp_models import SUPPORTED_WHISPER_CPP_MODELS

        resource_ids = [f"asr:whisper_cpp:{model.id}" for model in SUPPORTED_WHISPER_CPP_MODELS]
        self.assertGreaterEqual(Job.__table__.c.resource_id.type.length, max(map(len, resource_ids)))

    def test_series_position_is_unique_within_a_workspace(self) -> None:
        constraint_names = {constraint.name for constraint in Series.__table__.constraints}

        self.assertIn("uq_series_workspace_position", constraint_names)

class AlembicConfigurationTests(unittest.TestCase):
    def test_package_migration_directory_exposes_control_plane_revision(self) -> None:
        config = build_alembic_config(DatabaseOptions(url=MYSQL_URL))
        script = ScriptDirectory.from_config(config)

        self.assertEqual(script.get_current_head(), "0017_bilibili_inbox_series")

    def test_initial_migration_renders_mysql_ddl_without_a_running_server(self) -> None:
        config = build_alembic_config(DatabaseOptions(url=MYSQL_URL))
        output = StringIO()
        config.output_buffer = output

        command.upgrade(config, "head", sql=True)

        ddl = output.getvalue()
        self.assertIn("CREATE TABLE workspaces", ddl)
        self.assertIn("CREATE TABLE jobs", ddl)
        self.assertIn("CREATE TABLE outbox_events", ddl)
        self.assertIn("CREATE TABLE external_media_references", ddl)
        self.assertIn("CREATE TABLE legacy_migration_runs", ddl)
        self.assertIn("storage_mode", ddl)
        self.assertIn("LEFT JOIN notes AS note", ddl)
        self.assertIn("LEFT JOIN jobs AS job", ddl)
        self.assertIn("COALESCE(content_video.series_id, note_video.series_id)", ddl)
        self.assertIn("DEFAULT CURRENT_TIMESTAMP", ddl)
        self.assertIn("ALTER TABLE jobs MODIFY resource_id VARCHAR(128) NOT NULL", ddl)
        self.assertIn("bilibili_inbox", ddl)
        self.assertNotIn("CURRENT_TIMESTAMP(6)", ddl)


class ManagedLocalMySqlTests(unittest.TestCase):
    def test_uses_explicit_runtime_directory_from_environment(self) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"VSUMMARY_DATA": temp_dir}):
            self.assertEqual(_default_data_root(), Path(temp_dir))

    def test_data_paths_are_separate_from_the_installation_directory(self) -> None:
        paths = ManagedLocalMySqlPaths(Path("C:/Users/example/AppData/Local/VSummary"))

        self.assertEqual(paths.data_dir, paths.root / "mysql" / "data")
        self.assertEqual(paths.credential_path, paths.root / "mysql" / CREDENTIAL_FILE)
        self.assertEqual(paths.runtime_state_path, paths.root / "mysql" / "runtime.json")

    @unittest.skipUnless(os.name == "nt", "Windows MySQL path limitation")
    def test_rejects_non_ascii_mysql_paths_before_creating_data_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "测试" / "VSummary"
            mysql_home = root / "runtime" / "mysql"
            (mysql_home / "bin").mkdir(parents=True)
            (mysql_home / "bin" / "mysqld.exe").write_text("stub", encoding="utf-8")
            data_root = root / ".vsummary"
            runtime = ManagedLocalMySql(mysql_home=mysql_home, data_root=data_root)

            with self.assertRaisesRegex(ManagedLocalMySqlPathError, "纯英文路径"):
                runtime.start_and_migrate()

            self.assertFalse((data_root / "mysql").exists())

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

    def test_missing_runtime_state_reboots_application_account_before_writing_state(self) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mysql_home = root / "mysql-runtime"
            (mysql_home / "bin").mkdir(parents=True)
            (mysql_home / "bin" / "mysqld.exe").write_text("stub", encoding="utf-8")
            runtime = ManagedLocalMySql(mysql_home=mysql_home, data_root=root / "user-data")
            runtime._ensure_directories()
            (runtime.paths.data_dir / "auto.cnf").write_text("[auto]", encoding="utf-8")

            def complete_bootstrap(options: DatabaseOptions) -> None:
                runtime._write_runtime_state(options.parsed_url.port or 0)

            with (
                patch("backend.local.persistence.managed_mysql.load_local_mysql_password", return_value="secret"),
                patch("backend.local.persistence.managed_mysql._select_loopback_port", return_value=25331),
                patch.object(runtime, "_bootstrap_application_account", side_effect=complete_bootstrap) as bootstrap,
                patch.object(runtime, "_require_database_driver"),
                patch.object(runtime, "_validate_runtime_binary"),
                patch.object(runtime, "_acquire_instance_lock"),
                patch.object(runtime, "_release_instance_lock"),
                patch("backend.local.persistence.managed_mysql.upgrade_to_head"),
            ):
                options = runtime.start_and_migrate()

            self.assertEqual(options.parsed_url.port, 25331)
            self.assertEqual(options.parsed_url.password, "secret")
            bootstrap.assert_called_once_with(options)
            self.assertTrue(runtime.paths.runtime_state_path.is_file())

    def test_application_account_state_is_written_only_after_connection_verifies(self) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mysql_home = root / "mysql-runtime"
            (mysql_home / "bin").mkdir(parents=True)
            (mysql_home / "bin" / "mysqld.exe").write_text("stub", encoding="utf-8")
            runtime = ManagedLocalMySql(mysql_home=mysql_home, data_root=root / "user-data")
            runtime._ensure_directories()
            options = DatabaseOptions(url="mysql+pymysql://vsummary_app:secret@127.0.0.1:25331/vsummary")

            with (
                patch.object(runtime, "_write_bootstrap_sql") as write_bootstrap,
                patch.object(runtime, "_start_server") as start_server,
                patch.object(runtime, "_wait_for_database") as wait_for_database,
                patch.object(runtime, "_write_runtime_state") as write_state,
            ):
                runtime._bootstrap_application_account(options)

            write_bootstrap.assert_called_once_with("secret")
            start_server.assert_called_once_with(port=25331, init_file=runtime.paths.bootstrap_sql_path)
            wait_for_database.assert_called_once_with(options)
            write_state.assert_called_once_with(25331)

    def test_stop_does_not_shutdown_an_adopted_instance(self) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = ManagedLocalMySql(mysql_home=root / "mysql-runtime", data_root=root / "user-data")
            runtime._ensure_directories()
            runtime._write_runtime_state(25331)
            runtime._process = None

            with (
                patch("backend.local.persistence.managed_mysql.load_local_mysql_password", return_value="secret"),
                patch.object(runtime, "_shutdown_server") as shutdown,
            ):
                runtime.stop()

            shutdown.assert_not_called()

    def test_stop_shuts_down_the_actual_server_even_if_its_starting_parent_has_exited(self) -> None:
        from unittest.mock import Mock, patch

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = ManagedLocalMySql(mysql_home=root / "mysql-runtime", data_root=root / "user-data")
            runtime._ensure_directories()
            runtime._write_runtime_state(25331)
            runtime.paths.pid_path.write_text("9999", encoding="ascii")
            runtime._owns_server = True
            runtime._process = Mock()
            runtime._process.poll.return_value = 0

            with (
                patch("backend.local.persistence.managed_mysql.load_local_mysql_password", return_value="secret"),
                patch.object(runtime, "_shutdown_server") as shutdown,
                patch.object(runtime, "_wait_for_port_to_close"),
                patch.object(runtime, "_wait_for_server_exit"),
            ):
                runtime.stop()

            shutdown.assert_called_once()

    def test_existing_listening_database_is_adopted_without_starting_a_second_server(self) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = ManagedLocalMySql(mysql_home=root / "mysql-runtime", data_root=root / "user-data")
            with (
                patch("backend.local.persistence.managed_mysql._is_loopback_port_open", return_value=True),
                patch.object(runtime, "_start_server") as start_server,
            ):
                runtime._start_existing_instance(DatabaseOptions(url="mysql+pymysql://user:secret@127.0.0.1:25331/vsummary"))

            start_server.assert_not_called()


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


class OutboxWriteTests(unittest.TestCase):
    def test_workspace_scoped_outbox_helper_records_note_event(self) -> None:
        class SessionRecorder:
            def __init__(self) -> None:
                self.added: list[OutboxEvent] = []

            def add(self, row: OutboxEvent) -> None:
                self.added.append(row)

        session = SessionRecorder()
        occurred_at = datetime.now(timezone.utc)

        _enqueue_outbox_event(
            session,
            workspace_id="workspace-1",
            aggregate_type="note",
            aggregate_id="note-1",
            event_type="note_published",
            payload={"video_id": "video-1"},
            occurred_at=occurred_at,
        )

        self.assertEqual(len(session.added), 1)
        event = session.added[0]
        self.assertEqual(event.workspace_id, "workspace-1")
        self.assertEqual(event.aggregate_type, "note")
        self.assertEqual(event.aggregate_id, "note-1")
        self.assertEqual(event.payload, {"video_id": "video-1"})
        self.assertEqual(event.occurred_at, occurred_at)

    def test_workspace_scoped_outbox_helper_rejects_missing_workspace(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace_id"):
            _enqueue_outbox_event(
                object(),
                workspace_id="",
                aggregate_type="note",
                aggregate_id="note-1",
                event_type="note_published",
                payload={"video_id": "video-1"},
                occurred_at=datetime.now(timezone.utc),
            )
