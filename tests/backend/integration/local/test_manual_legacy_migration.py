from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import bindparam, select, text

from tests import _path_setup  # noqa: F401
from backend.local.legacy_migration import LegacyMigrationService
from backend.local.persistence.file_blob_store import FileBlobStore
from backend.core.ids import new_ulid
from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.database import DatabaseOptions, create_session_factory
from backend.video_summary.infrastructure.persistence.models import ExternalMediaReference, KnowledgeCard, MediaObject, Series, Video


@unittest.skipUnless(os.environ.get("VSUMMARY_TEST_MYSQL_URL"), "Disposable MySQL URL required")
class ManualLegacyMigrationE2ETests(unittest.TestCase):
    def test_three_modes_and_old_video_cleanup(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            old = root / "old"
            target = root / "new"
            blob_store = FileBlobStore(target / "runtime" / "blobs")
            copy_source = self._series(old, "copied", "copy", b"copied video")
            hard_source = self._series(old, "linked", "hardlink", b"hardlinked video")
            self._structured_artifacts(old, "copied")
            self._structured_artifacts(old, "linked")
            original = root / "original.mp4"
            hard_source.replace(original)
            os.link(original, hard_source)
            external = root / "external.mp4"
            external.write_bytes(b"external video")
            soft_dir = old / "workspace" / "external" / "lesson"
            soft_dir.mkdir(parents=True)
            (soft_dir.parent / "series_meta.json").write_text(json.dumps({"title": "external", "storage_mode": "external_reference"}), encoding="utf-8")
            (soft_dir / "source.json").write_text(json.dumps({"source_path": str(external)}), encoding="utf-8")
            model = old / "data" / "models" / "demo.bin"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"model data")
            session_id = new_ulid()
            sessions_dir = old / "data" / "agent_sessions"
            sessions_dir.mkdir(parents=True)
            (sessions_dir / "session.json").write_text(json.dumps({"session_id": session_id, "memory_key": "memory-e2e"}), encoding="utf-8")
            usage_db = old / "data" / "usage" / "llm_usage.sqlite3"
            usage_db.parent.mkdir(parents=True)
            connection = sqlite3.connect(usage_db)
            try:
                connection.execute("CREATE TABLE llm_usage (created_at TEXT, category TEXT, provider TEXT, base_url TEXT, model TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER)")
                connection.execute("INSERT INTO llm_usage VALUES ('2026-09-24 00:00:00','chat','e2e-provider','','e2e-model',2,3,5)")
                connection.commit()
            finally:
                connection.close()

            sessions = create_session_factory(DatabaseOptions(url=os.environ["VSUMMARY_TEST_MYSQL_URL"]))
            service = LegacyMigrationService(session_factory=sessions, blob_store=blob_store, installation_root=target)
            preview = service.inspect(old)
            self.assertEqual(preview["total_videos"], 3)
            run = service.create_run(old, include_data=["models"])
            service.start(run["id"])
            for _ in range(300):
                result = service.status(run["id"])
                if result["status"] != "running":
                    break
                time.sleep(0.1)

            self.assertEqual(result["status"], "completed", result["error"])
            self.assertEqual(result["removed_videos"], 2)
            self.assertFalse(copy_source.exists())
            self.assertFalse(hard_source.exists())
            self.assertFalse((old / "videos").exists())
            self.assertTrue(external.exists())
            self.assertEqual((target / "data" / "models" / "demo.bin").read_bytes(), b"model data")
            with sessions() as session:
                series = session.scalars(select(Series).where(Series.migration_run_id == run["id"])).all()
                series_ids = [item.id for item in series]
                media = session.scalars(select(MediaObject).join(Video, Video.id == MediaObject.video_id).where(Video.series_id.in_(series_ids))).all()
                references = session.scalars(select(ExternalMediaReference).join(Video, Video.id == ExternalMediaReference.video_id).where(Video.series_id.in_(series_ids))).all()
                cards = session.scalars(select(KnowledgeCard).join(Video, Video.id == KnowledgeCard.video_id).where(Video.series_id.in_(series_ids))).all()
                notes = session.execute(
                    text("SELECT n.id FROM notes n JOIN videos v ON v.id=n.video_id WHERE v.series_id IN :series_ids").bindparams(bindparam("series_ids", expanding=True)),
                    {"series_ids": series_ids},
                ).mappings().all()
                agent_session = session.execute(__import__("sqlalchemy").text("SELECT session_id FROM agent_session_snapshots WHERE session_id=:id"), {"id": session_id}).scalar()
            self.assertEqual(len(series), 3)
            self.assertTrue(all(item.import_published for item in series))
            self.assertEqual(len(media), 2)
            self.assertEqual(len(references), 1)
            self.assertEqual(len(cards), 4)
            self.assertEqual(len({card.id for card in cards}), 4)
            self.assertTrue(all(not card.id.startswith("kc-") for card in cards))
            self.assertEqual(len(notes), 2)
            self.assertEqual(len({note["id"] for note in notes}), 2)
            self.assertTrue(all(not note["id"].startswith("note-") for note in notes))
            self.assertTrue(all(set(card.related_card_ids).issubset({other.id for other in cards if other.video_id == card.video_id}) for card in cards))
            self.assertEqual(agent_session, session_id)
            self.assertTrue(any(path.samefile(original) for path in blob_store.root.glob("objects/media/*/source.mp4")))
            self.assertEqual(Path(references[0].source_path), external)

    def test_resume_after_old_video_was_deleted_before_checkpoint(self) -> None:
        class InterruptAfterDelete(LegacyMigrationService):
            interrupted = False

            def _save_manifest(self, run_id, manifest):
                if not self.interrupted and any(media["state"] == "source_removed" for series in manifest["series"] for media in series["media"]):
                    self.interrupted = True
                    raise RuntimeError("simulated interruption after source deletion")
                return super()._save_manifest(run_id, manifest)

        with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            old = root / "old"
            first = self._series(old, "course", "copy", b"first video")
            second = first.with_name("second.mp4")
            second.write_bytes(b"second video")
            sessions = create_session_factory(DatabaseOptions(url=os.environ["VSUMMARY_TEST_MYSQL_URL"]))
            blob_store = FileBlobStore(root / "new" / "runtime" / "blobs")
            failing = InterruptAfterDelete(session_factory=sessions, blob_store=blob_store, installation_root=root / "new")
            run = failing.create_run(old, include_data=[])
            failing.start(run["id"])
            failed = self._wait(failing, run["id"])
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["manifest"]["series"][0]["media"][0]["state"], "verified")
            self.assertFalse(first.exists())
            self.assertTrue(second.exists())

            resumed = LegacyMigrationService(session_factory=sessions, blob_store=blob_store, installation_root=root / "new")
            resumed.start(run["id"])
            completed = self._wait(resumed, run["id"])
            self.assertEqual(completed["status"], "completed", completed["error"])
            self.assertEqual(completed["removed_videos"], 2)
            self.assertFalse(second.exists())

    def test_completed_source_can_create_a_new_migration_run(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            old = root / "old"
            self._series(old, "first", "copy", b"first video")
            sessions = create_session_factory(DatabaseOptions(url=os.environ["VSUMMARY_TEST_MYSQL_URL"]))
            service = LegacyMigrationService(
                session_factory=sessions,
                blob_store=FileBlobStore(root / "new" / "runtime" / "blobs"),
                installation_root=root / "new",
            )
            first_run = service.create_run(old, include_data=[])
            service.start(first_run["id"])
            self.assertEqual(self._wait(service, first_run["id"])["status"], "completed")

            self._series(old, "second", "copy", b"second video")
            second_run = service.create_run(old, include_data=[])

            self.assertNotEqual(second_run["id"], first_run["id"])
            self.assertEqual(second_run["status"], "ready")
            self.assertEqual(second_run["total_videos"], 1)

    def test_legacy_position_skips_soft_deleted_series_positions(self) -> None:
        sessions = create_session_factory(DatabaseOptions(url=os.environ["VSUMMARY_TEST_MYSQL_URL"]))
        control = SqlControlPlaneRepository(sessions)
        workspace_id = control.create_workspace(owner_scope_id=f"migration-position-{new_ulid()}", title="Migration position test")
        old_series_id = control.create_series(workspace_id=workspace_id, title="Old", position=4)
        with sessions.begin() as session:
            session.execute(
                __import__("sqlalchemy").text("UPDATE series SET deleted_at=NOW() WHERE id=:series"),
                {"series": old_series_id},
            )

        new_series_id = control.create_series_at_preferred_position(
            workspace_id=workspace_id,
            title="Migrated",
            preferred_position=4,
            migration_run_id=new_ulid(),
        )

        with sessions() as session:
            position = session.execute(
                __import__("sqlalchemy").text("SELECT position FROM series WHERE id=:series"),
                {"series": new_series_id},
            ).scalar_one()
        self.assertEqual(position, 5)

    @staticmethod
    def _wait(service: LegacyMigrationService, run_id: str) -> dict:
        for _ in range(300):
            status = service.status(run_id)
            if status["status"] != "running":
                return status
            time.sleep(0.1)
        raise AssertionError("migration did not reach a terminal state")

    @staticmethod
    def _series(root: Path, name: str, mode: str, content: bytes) -> Path:
        media = root / "videos" / name / "lesson.mp4"
        media.parent.mkdir(parents=True)
        media.write_bytes(content)
        workspace = root / "workspace" / name
        workspace.mkdir(parents=True)
        (workspace / "series_meta.json").write_text(json.dumps({"title": name, "storage_mode": mode}), encoding="utf-8")
        return media

    @staticmethod
    def _structured_artifacts(root: Path, series: str) -> None:
        video_root = root / "workspace" / series / "lesson"
        video_root.mkdir()
        (video_root / "knowledge_cards.json").write_text(
            json.dumps(
                {
                    "title": "旧知识卡片",
                    "cards": [
                        {"id": "kc-1", "title": "第一张", "related_card_ids": ["kc-2"]},
                        {"id": "kc-2", "title": "第二张", "related_card_ids": ["kc-1"]},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (video_root / "notes.json").write_text(
            json.dumps({"notes": [{"id": "note-1", "title": "旧笔记", "content": "内容", "source": "manual"}]}),
            encoding="utf-8",
        )
