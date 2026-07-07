from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch


from backend.api.bootstrap import LazyAgentRuntimeProvider, _WorkspaceIndexRefresher
from backend.video_summary.infrastructure.agent_memory.retrieval import SeriesRetrievalService
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.library.models import (
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
    VideoKnowledgeCardsDTO,
    VideoNoteDTO,
    VideoNotesDTO,
    VideoSummaryDTO,
    VideoTranscriptDTO,
    WorkspaceDTO,
)
from backend.video_summary.library.usecases.series_synopsis_generation import (
    RefreshSeriesKnowledgeMemory,
    build_series_catalog_payload,
)
from backend.video_summary.library.usecases.summary_generation import (
    GenerateVideoSummaryFromLibrary,
)
from backend.video_summary.library.usecases.knowledge_cards import GenerateVideoKnowledgeCards
from backend.video_summary.library.usecases.imports import (
    ImportLocalPlaygroundVideos,
    ImportLocalSeries,
    ImportLocalSeriesVideos,
)
from backend.video_summary.library.usecases.mutations import DeleteSeries, DeleteVideoSource
from backend.video_summary.library.usecases.notes import CreateVideoNote, DeleteVideoNote, UpdateVideoNote


def _gitignored_temp_parent() -> Path:
    temp_parent = Path("temp")
    temp_parent.mkdir(exist_ok=True)
    return temp_parent


class SeriesKnowledgeMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_series_catalog_payload_reuses_existing_summary_fields(self) -> None:
        workspace = FakeSeriesWorkspace()

        payload = build_series_catalog_payload(
            workspace,
            "series-1",
            updated_at="2026-05-03T00:00:00Z",
        )

        self.assertEqual(payload["series_id"], "series-1")
        self.assertEqual(payload["series_title"], "Series 1")
        self.assertEqual(payload["updated_at"], "2026-05-03T00:00:00Z")
        self.assertEqual(
            payload["videos"],
            [
                {
                    "video_id": "video-1",
                    "title": "Video 1",
                    "one_sentence_summary": "概况一",
                    "chapter_titles": ["第一章", "第二章"],
                    "processed": True,
                },
                {
                    "video_id": "video-2",
                    "title": "Video 2",
                    "one_sentence_summary": "",
                    "chapter_titles": [],
                    "processed": False,
                },
            ],
        )

    async def test_generate_video_summary_triggers_series_memory_refresh(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeSeriesWorkspace()
        generator = CompletedGenerator()
        refresher = FakeSeriesKnowledgeMemoryRefresher()
        use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            series_memory_refresher=refresher,
        )

        result = await use_case.run("series-1", "video-1")
        self.assertIsNotNone(result)
        self.assertEqual(refresher.calls, [("series-1", "video-1")])

    async def test_refresh_failure_does_not_turn_video_generation_into_failed_result(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeSeriesWorkspace()
        generator = CompletedGenerator()
        refresher = FailingSeriesKnowledgeMemoryRefresher()
        use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            series_memory_refresher=refresher,
        )

        result = await use_case.run("series-1", "video-1")

        self.assertIsNotNone(result)
        self.assertEqual(result.video_id, "video-1")

    async def test_refresh_series_knowledge_memory_rebuilds_catalog_and_refreshes_index(self) -> None:
        workspace = FakeSeriesWorkspace()
        index_refresher = FakeIndexRefresher()
        refresher = RefreshSeriesKnowledgeMemory(
            workspace=workspace,
            index_refresher=index_refresher,
        )

        refresher.refresh("series-1", "video-1")

        self.assertEqual(
            workspace.saved_catalogs["series-1"]["videos"][0]["one_sentence_summary"],
            "概况一",
        )
        self.assertEqual(index_refresher.video_upserts, [("series-1", "video-1")])


class FileSystemSeriesAssetRoundTripTests(unittest.TestCase):
    def test_round_trip_series_catalog_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            workspace = FileSystemVideoWorkspace(root_dir)

            catalog_payload = {
                "series_id": "series-1",
                "series_title": "Series 1",
                "videos": [],
                "updated_at": "2026-05-03T00:00:00Z",
            }
            workspace.save_series_catalog("series-1", catalog_payload)

            self.assertEqual(workspace.get_series_catalog("series-1"), catalog_payload)

    def test_invalid_series_catalog_payload_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            workspace = FileSystemVideoWorkspace(root_dir)

            with self.assertRaises(Exception):
                workspace.save_series_catalog(
                    "series-1",
                    {
                        "series_id": "series-1",
                        "series_title": "Series 1",
                        "videos": [
                            {
                                "video_id": "video-1",
                                "title": "Video 1",
                                "one_sentence_summary": "ok",
                                "chapter_titles": "not-a-list",
                                "processed": True,
                            }
                        ],
                        "updated_at": "2026-05-03T00:00:00Z",
                    },
                )


class RetrievalIndexLifecycleTests(unittest.TestCase):
    def test_search_reranks_twenty_embedding_candidates_down_to_five_hits(self) -> None:
        reranker = FakeReranker(
            {
                "candidate 3": 0.99,
                "candidate 7": 0.98,
                "candidate 11": 0.97,
                "candidate 15": 0.96,
                "candidate 19": 0.95,
            }
        )
        with tempfile.TemporaryDirectory(dir=_gitignored_temp_parent()) as temp_dir:
            service = SeriesRetrievalService(
                workspace=FakeSeriesWorkspace(),
                db_uri=temp_dir,
                reranker=reranker,
                rerank_enabled=True,
            )
            service._index = FakeVectorIndex(  # type: ignore[attr-defined]
                [
                    FakeRetrievedNode(text=f"candidate {index}", score=1.0 / index)
                    for index in range(1, 31)
                ]
            )

            with patch.object(service, "_is_series_signature_stale", return_value=False):
                response = service.search(
                    scope_type="series",
                    series_id="series-1",
                    video_id="",
                    query="这个系列讲了啥",
                    target_source="all",
                    source_tags=[],
                    expand_context=False,
                    context_window_seconds=120,
                    max_hits=5,
                )

        self.assertEqual(service._index.last_similarity_top_k, 20)  # type: ignore[attr-defined]
        self.assertEqual(len(reranker.calls[0]["texts"]), 20)
        self.assertEqual(
            [hit["text"] for hit in response["hits"]],
            ["candidate 3", "candidate 7", "candidate 11", "candidate 15", "candidate 19"],
        )
        self.assertEqual([hit["evidence_id"] for hit in response["hits"]], ["e1", "e2", "e3", "e4", "e5"])

    def test_search_without_rerank_uses_max_hits_as_embedding_top_k(self) -> None:
        reranker = FakeReranker({"candidate 10": 1.0})
        with tempfile.TemporaryDirectory(dir=_gitignored_temp_parent()) as temp_dir:
            service = SeriesRetrievalService(
                workspace=FakeSeriesWorkspace(),
                db_uri=temp_dir,
                reranker=reranker,
                rerank_enabled=False,
            )
            service._index = FakeVectorIndex(  # type: ignore[attr-defined]
                [
                    FakeRetrievedNode(text=f"candidate {index}", score=1.0 / index)
                    for index in range(1, 31)
                ]
            )

            with patch.object(service, "_is_series_signature_stale", return_value=False):
                response = service.search(
                    scope_type="series",
                    series_id="series-1",
                    video_id="",
                    query="这个系列讲了啥",
                    target_source="all",
                    source_tags=[],
                    expand_context=False,
                    context_window_seconds=120,
                    max_hits=5,
                )

        self.assertEqual(service._index.last_similarity_top_k, 5)  # type: ignore[attr-defined]
        self.assertEqual(reranker.calls, [])
        self.assertEqual(
            [hit["text"] for hit in response["hits"]],
            ["candidate 1", "candidate 2", "candidate 3", "candidate 4", "candidate 5"],
        )

    def test_search_builds_current_series_index_when_missing(self) -> None:
        workspace = FakeSeriesWorkspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(
                workspace=workspace,
                db_uri=temp_dir,
            )

            response = service.search(
                scope_type="series",
                series_id="series-1",
                video_id="",
                query="这个系列讲了啥",
                target_source="all",
                source_tags=[],
                expand_context=False,
                context_window_seconds=120,
                max_hits=5,
            )
            self.assertTrue(response["hits"])

    def test_search_existing_series_survives_unrelated_pending_series_import_after_restart(self) -> None:
        workspace = MutableRetrievalWorkspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(workspace=workspace, db_uri=temp_dir)
            service.refresh_all()

            workspace.add_pending_series("series-new")
            restarted_service = SeriesRetrievalService(workspace=workspace, db_uri=temp_dir)

            response = restarted_service.search(
                scope_type="series",
                series_id="series-1",
                video_id="",
                query="任意问题",
                target_source="all",
                source_tags=[],
                expand_context=False,
                context_window_seconds=120,
                max_hits=20,
            )

            doc_ids = {hit["doc_id"] for hit in response["hits"]}
            self.assertIn("series:series-1:video:video-1:summary_global", doc_ids)


class RetrievalIncrementalMutationTests(unittest.TestCase):
    def test_full_refresh_indexes_multiple_videos_summary_and_transcript_assets(self) -> None:
        workspace = MutableRetrievalWorkspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(workspace=workspace, db_uri=temp_dir)

            service.refresh_all()
            response = service.search(
                scope_type="series",
                series_id="series-1",
                video_id="",
                query="任意问题",
                target_source="all",
                source_tags=[],
                expand_context=False,
                context_window_seconds=120,
                max_hits=20,
            )

            doc_ids = {hit["doc_id"] for hit in response["hits"]}
            self.assertIn("series:series-1:video:video-1:summary_global", doc_ids)
            self.assertIn("series:series-1:video:video-1:transcript:0.0-5.0", doc_ids)
            self.assertIn("series:series-1:video:video-2:summary_global", doc_ids)
            self.assertIn("series:series-1:video:video-2:transcript:5.0-10.0", doc_ids)

    def test_upsert_video_updates_one_video_and_preserves_another_video_hits(self) -> None:
        workspace = MutableRetrievalWorkspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(workspace=workspace, db_uri=temp_dir)
            service.refresh_all()
            workspace.update_video_summary_text("series-1", "video-1", "新的概况一")

            service.upsert_video("series-1", "video-1")
            response = service.search(
                scope_type="series",
                series_id="series-1",
                video_id="",
                query="任意问题",
                target_source="all",
                source_tags=[],
                expand_context=False,
                context_window_seconds=120,
                max_hits=20,
            )

            texts_by_doc_id = {hit["doc_id"]: hit["text"] for hit in response["hits"]}
            self.assertEqual(texts_by_doc_id["series:series-1:video:video-1:summary_global"], "新的概况一")
            self.assertEqual(texts_by_doc_id["series:series-1:video:video-2:summary_global"], "概况二")

    def test_delete_video_removes_only_target_video_hits(self) -> None:
        workspace = MutableRetrievalWorkspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(workspace=workspace, db_uri=temp_dir)
            service.refresh_all()

            service.delete_video("series-1", "video-1")
            response = service.search(
                scope_type="series",
                series_id="series-1",
                video_id="",
                query="任意问题",
                target_source="all",
                source_tags=[],
                expand_context=False,
                context_window_seconds=120,
                max_hits=20,
            )

            remaining_doc_ids = {hit["doc_id"] for hit in response["hits"]}
            self.assertNotIn("series:series-1:video:video-1:summary_global", remaining_doc_ids)
            self.assertIn("series:series-1:video:video-2:summary_global", remaining_doc_ids)

    def test_delete_series_removes_only_target_series_hits(self) -> None:
        workspace = MutableRetrievalWorkspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(workspace=workspace, db_uri=temp_dir)
            service.refresh_all()

            service.delete_series("series-1")
            response = service.search(
                scope_type="series",
                series_id="series-2",
                video_id="",
                query="任意问题",
                target_source="all",
                source_tags=[],
                expand_context=False,
                context_window_seconds=120,
                max_hits=20,
            )

            remaining_doc_ids = {hit["doc_id"] for hit in response["hits"]}
            self.assertFalse(any(doc_id.startswith("series:series-1:") for doc_id in remaining_doc_ids))
            self.assertTrue(any(doc_id.startswith("series:series-2:") for doc_id in remaining_doc_ids))

    def test_delete_series_optimizes_table_after_incremental_delete(self) -> None:
        service = SeriesRetrievalService(workspace=MutableRetrievalWorkspace(), db_uri="db-uri")

        with (
            patch("backend.video_summary.infrastructure.agent_memory.retrieval._table_exists", return_value=True),
            patch(
                "backend.video_summary.infrastructure.agent_memory.retrieval._read_signature_file",
                return_value={"series-1": ("series-1:video-1:ready:1:a:b:c:d",)},
            ),
            patch("backend.video_summary.infrastructure.agent_memory.retrieval._delete_rows"),
            patch("backend.video_summary.infrastructure.agent_memory.retrieval._write_signature_file"),
            patch(
                "backend.video_summary.infrastructure.agent_memory.retrieval._optimize_lancedb_table",
                create=True,
            ) as optimize_table,
        ):
            service.delete_series("series-1")

        optimize_table.assert_called_once_with("db-uri", "agent_graph_evidence_v4")

    def test_delete_series_does_not_fail_when_lancedb_optimize_fails(self) -> None:
        service = SeriesRetrievalService(workspace=MutableRetrievalWorkspace(), db_uri="db-uri")

        with (
            patch("backend.video_summary.infrastructure.agent_memory.retrieval._table_exists", return_value=True),
            patch(
                "backend.video_summary.infrastructure.agent_memory.retrieval._read_signature_file",
                return_value={"series-1": ("series-1:video-1:ready:1:a:b:c:d",)},
            ),
            patch("backend.video_summary.infrastructure.agent_memory.retrieval._delete_rows") as delete_rows,
            patch("backend.video_summary.infrastructure.agent_memory.retrieval._write_signature_file"),
            patch(
                "backend.video_summary.infrastructure.agent_memory.retrieval._optimize_lancedb_table",
                side_effect=RuntimeError("optimize failed"),
            ) as optimize_table,
        ):
            service.delete_series("series-1")

        delete_rows.assert_called_once()
        optimize_table.assert_called_once_with("db-uri", "agent_graph_evidence_v4")

    def test_full_refresh_uses_stable_business_doc_ids(self) -> None:
        workspace = MutableRetrievalWorkspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(workspace=workspace, db_uri=temp_dir)

            service.refresh_all()

            import lancedb

            table = lancedb.connect(temp_dir).open_table("agent_graph_evidence_v4")
            rows = table.to_pandas().to_dict(orient="records")
            top_level_doc_ids = {row["doc_id"] for row in rows}
            metadata_doc_ids = {row["metadata"]["doc_id"] for row in rows}
            self.assertIn("series:series-1:video:video-1:summary_global", top_level_doc_ids)
            self.assertIn("series:series-1:video:video-1:summary_global", metadata_doc_ids)

    def test_upsert_video_rebuilds_index_when_index_table_is_missing(self) -> None:
        workspace = MutableRetrievalWorkspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(workspace=workspace, db_uri=temp_dir)

            service.upsert_video("series-1", "video-1")
            response = service.search(
                scope_type="series",
                series_id="series-1",
                video_id="",
                query="任意问题",
                target_source="all",
                source_tags=[],
                expand_context=False,
                context_window_seconds=120,
                max_hits=20,
            )

            self.assertTrue(response["hits"])

    def test_refresh_uses_vector_store_overwrite_without_pre_drop(self) -> None:
        workspace = FakeSeriesWorkspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(
                workspace=workspace,
                db_uri=temp_dir,
            )

            with patch(
                "backend.video_summary.infrastructure.agent_memory.retrieval._reset_lancedb_table",
                side_effect=AssertionError("refresh should not manually drop the table"),
            ):
                service.refresh()

            response = service.search(
                scope_type="series",
                series_id="series-1",
                video_id="",
                query="这个系列讲了啥",
                target_source="all",
                source_tags=[],
                expand_context=False,
                context_window_seconds=120,
                max_hits=5,
            )
            self.assertTrue(response["hits"])


class WorkspaceIndexRefreshStatusTests(unittest.TestCase):
    def test_refresher_reports_running_and_completed_status(self) -> None:
        tracker = InMemoryProgressTracker()
        calls: list[str] = []
        started = threading.Event()
        release = threading.Event()

        def refresh_indexes() -> None:
            calls.append("refresh")
            started.set()
            self.assertTrue(release.wait(2.0))

        refresher = _WorkspaceIndexRefresher(
            refresh_all=refresh_indexes,
            upsert_video=lambda series_id, video_id: None,
            delete_video=lambda series_id, video_id: None,
            delete_series=lambda series_id: None,
            progress_tracker=tracker,
        )

        refresher.refresh()

        self.assertTrue(started.wait(2.0))
        self.assertEqual(tracker.get_snapshot("agent-memory-refresh").status, "running")
        release.set()
        self.assertTrue(_wait_until(lambda: tracker.get_snapshot("agent-memory-refresh").status == "completed"))
        self.assertEqual(calls, ["refresh"])

    def test_refresher_reports_failed_status(self) -> None:
        tracker = InMemoryProgressTracker()

        def refresh_indexes() -> None:
            raise RuntimeError("boom")

        refresher = _WorkspaceIndexRefresher(
            refresh_all=refresh_indexes,
            upsert_video=lambda series_id, video_id: None,
            delete_video=lambda series_id, video_id: None,
            delete_series=lambda series_id: None,
            progress_tracker=tracker,
        )

        refresher.refresh()

        self.assertTrue(_wait_until(lambda: tracker.get_snapshot("agent-memory-refresh").status == "failed"))
        self.assertEqual(tracker.get_snapshot("agent-memory-refresh").error, "boom")

    def test_refresher_runs_one_follow_up_refresh_when_called_again_while_busy(self) -> None:
        tracker = InMemoryProgressTracker()
        calls: list[str] = []
        started = threading.Event()
        release = threading.Event()
        first_call_gate = threading.Event()

        def refresh_indexes() -> None:
            calls.append("refresh")
            started.set()
            if len(calls) == 1:
                first_call_gate.set()
                self.assertTrue(release.wait(2.0))

        refresher = _WorkspaceIndexRefresher(
            refresh_all=refresh_indexes,
            upsert_video=lambda series_id, video_id: None,
            delete_video=lambda series_id, video_id: None,
            delete_series=lambda series_id: None,
            progress_tracker=tracker,
        )

        refresher.refresh()
        self.assertTrue(first_call_gate.wait(2.0))
        refresher.refresh()
        release.set()

        self.assertTrue(_wait_until(lambda: len(calls) == 2))


class WorkspaceIndexOperationQueueTests(unittest.TestCase):
    def test_four_video_upserts_drain_as_one_batch_and_report_zero_of_n_progress(self) -> None:
        tracker = InMemoryProgressTracker()
        executed: list[tuple[str, str]] = []
        observed_details: list[str | None] = []

        with _patched_thread_start() as scheduled_targets:
            refresher = _WorkspaceIndexRefresher(
                refresh_all=lambda: None,
                upsert_video=lambda series_id, video_id: _record_upsert(
                    tracker,
                    executed,
                    observed_details,
                    series_id,
                    video_id,
                ),
                delete_video=lambda series_id, video_id: None,
                delete_series=lambda series_id: None,
                progress_tracker=tracker,
            )
            refresher.upsert_video("series-1", "video-1")
            refresher.upsert_video("series-1", "video-2")
            refresher.upsert_video("series-1", "video-3")
            refresher.upsert_video("series-1", "video-4")

        self.assertEqual(len(scheduled_targets), 1)
        scheduled_targets[0]()

        self.assertEqual(
            executed,
            [
                ("series-1", "video-1"),
                ("series-1", "video-2"),
                ("series-1", "video-3"),
                ("series-1", "video-4"),
            ],
        )
        self.assertIsNotNone(observed_details[0])
        self.assertIn("0/4", observed_details[0])
        self.assertEqual(tracker.get_snapshot("agent-memory-refresh").status, "completed")

    def test_duplicate_same_video_upserts_coalesce_into_one_operation(self) -> None:
        tracker = InMemoryProgressTracker()
        executed: list[tuple[str, str]] = []

        with _patched_thread_start() as scheduled_targets:
            refresher = _WorkspaceIndexRefresher(
                refresh_all=lambda: None,
                upsert_video=lambda series_id, video_id: executed.append((series_id, video_id)),
                delete_video=lambda series_id, video_id: None,
                delete_series=lambda series_id: None,
                progress_tracker=tracker,
            )
            refresher.upsert_video("series-1", "video-1")
            refresher.upsert_video("series-1", "video-1")

        scheduled_targets[0]()
        self.assertEqual(executed, [("series-1", "video-1")])

    def test_delete_supersedes_pending_upsert_for_same_video(self) -> None:
        tracker = InMemoryProgressTracker()
        executed: list[tuple[str, str, str | None]] = []

        with _patched_thread_start() as scheduled_targets:
            refresher = _WorkspaceIndexRefresher(
                refresh_all=lambda: None,
                upsert_video=lambda series_id, video_id: executed.append(("upsert", series_id, video_id)),
                delete_video=lambda series_id, video_id: executed.append(("delete", series_id, video_id)),
                delete_series=lambda series_id: None,
                progress_tracker=tracker,
            )
            refresher.upsert_video("series-1", "video-1")
            refresher.delete_video("series-1", "video-1")

        scheduled_targets[0]()
        self.assertEqual(executed, [("delete", "series-1", "video-1")])

    def test_full_rebuild_supersedes_pending_incremental_operations(self) -> None:
        tracker = InMemoryProgressTracker()
        executed: list[str] = []

        with _patched_thread_start() as scheduled_targets:
            refresher = _WorkspaceIndexRefresher(
                refresh_all=lambda: executed.append("full_rebuild"),
                upsert_video=lambda series_id, video_id: executed.append(f"upsert:{series_id}/{video_id}"),
                delete_video=lambda series_id, video_id: executed.append(f"delete:{series_id}/{video_id}"),
                delete_series=lambda series_id: executed.append(f"delete_series:{series_id}"),
                progress_tracker=tracker,
            )
            refresher.upsert_video("series-1", "video-1")
            refresher.upsert_video("series-1", "video-2")
            refresher.refresh_all()

        scheduled_targets[0]()
        self.assertEqual(executed, ["full_rebuild"])


class LazyAgentRuntimeProviderTests(unittest.TestCase):
    def test_workspace_index_refresh_does_not_hold_runtime_lock(self) -> None:
        test_case = self
        started = threading.Event()
        release = threading.Event()
        invalidated = threading.Event()

        class FakeRetrievalService:
            def invalidate(self) -> None:
                invalidated.set()

        class BlockingIndexBuilder:
            def __init__(self, *, retrieval_service: FakeRetrievalService) -> None:
                self._retrieval_service = retrieval_service

            def refresh(self) -> None:
                started.set()
                test_case.assertIsNotNone(self._retrieval_service)
                test_case.assertTrue(release.wait(2.0))

        with tempfile.TemporaryDirectory() as temp_dir:
            provider = LazyAgentRuntimeProvider(
                root_dir=Path(temp_dir),
                workspace=FakeSeriesWorkspace(),
            )

            with (
                patch("backend.api.bootstrap.SeriesRetrievalService", return_value=FakeRetrievalService()),
                patch("backend.api.bootstrap.AgentWorkspaceIndexBuilder", BlockingIndexBuilder),
            ):
                refresh_thread = threading.Thread(target=provider.refresh_workspace_indexes)
                refresh_thread.start()

                self.assertTrue(started.wait(2.0))
                invalidate_thread = threading.Thread(target=provider.invalidate_workspace_indexes)
                invalidate_thread.start()

                self.assertTrue(invalidated.wait(0.5))
                release.set()
                refresh_thread.join(2.0)
                invalidate_thread.join(2.0)
                self.assertFalse(refresh_thread.is_alive())
                self.assertFalse(invalidate_thread.is_alive())


class ImportAndMutationRefreshPolicyTests(unittest.TestCase):
    def test_delete_video_source_rejects_active_video_generation(self) -> None:
        workspace = FakeMutationWorkspace()
        guard = FakeGenerationActivityChecker(active_videos={("series-1", "video-1")})

        use_case = DeleteVideoSource(workspace, FakeIndexRefresher(), generation_activity_checker=guard)

        with self.assertRaisesRegex(RuntimeError, "正在生成"):
            use_case.run("series-1", "video-1")
        self.assertEqual(workspace.deleted_videos, [])

    def test_delete_video_source_rejects_active_series_generation(self) -> None:
        workspace = FakeMutationWorkspace()
        guard = FakeGenerationActivityChecker(active_series={"series-1"})

        use_case = DeleteVideoSource(workspace, FakeIndexRefresher(), generation_activity_checker=guard)

        with self.assertRaisesRegex(RuntimeError, "正在生成"):
            use_case.run("series-1", "video-2")
        self.assertEqual(workspace.deleted_videos, [])

    def test_delete_series_rejects_active_series_generation(self) -> None:
        workspace = FakeMutationWorkspace()
        guard = FakeGenerationActivityChecker(active_series={"series-1"})

        use_case = DeleteSeries(workspace, FakeIndexRefresher(), generation_activity_checker=guard)

        with self.assertRaisesRegex(RuntimeError, "正在生成"):
            use_case.run("series-1")
        self.assertEqual(workspace.deleted_series, [])

    def test_import_does_not_trigger_index_refresh(self) -> None:
        refresher = FakeIndexRefresher()
        workspace = FakeImportWorkspace()

        ImportLocalSeries(workspace).run(title="Series", files=[("a.mp4", object())])
        ImportLocalPlaygroundVideos(workspace).run(files=[("b.mp4", object())])
        ImportLocalSeriesVideos(workspace).run(series_id="series-1", files=[("c.mp4", object())])

        self.assertEqual(refresher.refresh_calls, 0)

    def test_delete_only_refreshes_when_processed_assets_are_removed(self) -> None:
        refresher = FakeIndexRefresher()
        workspace = FakeMutationWorkspace()

        DeleteVideoSource(workspace, refresher).run("series-1", "video-unprocessed")
        self.assertEqual(refresher.refresh_calls, 0)
        self.assertEqual(refresher.video_deletes, [])

        DeleteVideoSource(workspace, refresher).run("series-1", "video-processed")
        self.assertEqual(refresher.video_deletes, [("series-1", "video-processed")])

        DeleteSeries(workspace, refresher).run("series-2")
        self.assertEqual(refresher.series_deletes, [])

        workspace = FakeMutationWorkspace()
        DeleteSeries(workspace, refresher).run("series-1")
        self.assertEqual(refresher.series_deletes, ["series-1"])


class IncrementalQueueWiringTests(unittest.TestCase):
    def test_knowledge_cards_queue_video_upsert(self) -> None:
        refresher = FakeIndexRefresher()
        workspace = FakeKnowledgeCardWorkspace()
        generator = FakeKnowledgeCardGenerator()

        result = GenerateVideoKnowledgeCards(workspace, generator, refresher).run("series-1", "video-1")

        self.assertIsNotNone(result)
        self.assertEqual(refresher.video_upserts, [("series-1", "video-1")])

    def test_note_mutations_queue_video_upsert(self) -> None:
        refresher = FakeIndexRefresher()
        workspace = FakeNotesMutationWorkspace()

        CreateVideoNote(workspace, refresher).run("series-1", "video-1", title="n1", content="c1", source="manual")
        UpdateVideoNote(workspace, refresher).run("series-1", "video-1", "note-1", title="n2", content="c2")
        DeleteVideoNote(workspace, refresher).run("series-1", "video-1", "note-1")

        self.assertEqual(
            refresher.video_upserts,
            [
                ("series-1", "video-1"),
                ("series-1", "video-1"),
                ("series-1", "video-1"),
            ],
        )



class FakeSeriesWorkspace:
    def __init__(self) -> None:
        self._workspace = WorkspaceDTO(id="workspace", title="Workspace")
        self._series = [
            LibrarySeriesDTO(
                id="series-1",
                title="Series 1",
                videos=[
                    LibraryVideoCardDTO(
                        id="video-1",
                        title="Video 1",
                        source_name="video-1.mp4",
                        processed=True,
                        status="ready",
                    ),
                    LibraryVideoCardDTO(
                        id="video-2",
                        title="Video 2",
                        source_name="video-2.mp4",
                        processed=False,
                        status="pending",
                    ),
                ],
            )
        ]
        self.saved_catalogs: dict[str, dict[str, object]] = {}

    def get_workspace(self) -> WorkspaceDTO:
        return self._workspace

    def list_series(self) -> list[LibrarySeriesDTO]:
        return self._series

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        if video_id != "video-1":
            return None
        return VideoSummaryDTO(
            series_id=series_id,
            video_id=video_id,
            title="Video 1",
            summary={
                "title": "Video 1",
                "one_sentence_summary": "概况一",
                "chapters": [
                    {"title": "第一章", "transcript_segments": [{"text": "不应进入 catalog"}]},
                    {"title": "第二章"},
                ],
            },
        )

    def get_video_transcript(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        del series_id, video_id
        return None

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        del series_id, video_id
        return None

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        del series_id, video_id
        return None

    def save_series_catalog(self, series_id: str, payload: dict[str, object]) -> None:
        self.saved_catalogs[series_id] = payload


class FakeReranker:
    def __init__(self, scores_by_text: dict[str, float]) -> None:
        self.scores_by_text = scores_by_text
        self.calls: list[dict[str, object]] = []

    def score(self, *, query: str, texts: list[str]) -> list[float]:
        self.calls.append({"query": query, "texts": list(texts)})
        return [self.scores_by_text.get(text, 0.0) for text in texts]


class FakeVectorIndex:
    def __init__(self, nodes: list["FakeRetrievedNode"]) -> None:
        self.nodes = nodes
        self.last_similarity_top_k: int | None = None

    def as_retriever(self, *, similarity_top_k: int, filters) -> "FakeRetriever":
        del filters
        self.last_similarity_top_k = similarity_top_k
        return FakeRetriever(self.nodes[:similarity_top_k])


class FakeRetriever:
    def __init__(self, nodes: list["FakeRetrievedNode"]) -> None:
        self.nodes = nodes

    def retrieve(self, query: str) -> list["FakeRetrievedNode"]:
        del query
        return self.nodes


class FakeRetrievedNode:
    def __init__(self, *, text: str, score: float) -> None:
        self.score = score
        self.node = FakeNode(text)


class FakeNode:
    def __init__(self, text: str) -> None:
        self._text = text
        self.metadata = {
            "doc_id": f"doc:{text}",
            "series_id": "series-1",
            "video_id": text.replace("candidate ", "video-"),
            "title": text,
            "source_type": "summary_global",
            "source_family": "summary",
        }

    def get_content(self) -> str:
        return self._text


class FakeProgressTracker:
    def create_reporter(self, task_id: str) -> "FakeReporter":
        return FakeReporter()


class FakeReporter:
    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        return None

    def completed(self, detail: str | None = None) -> None:
        return None

    def failed(self, message: str) -> None:
        return None

    def cancelled(self, detail: str | None = None) -> None:
        return None

    def is_cancel_requested(self) -> bool:
        return False

    def raise_if_cancelled(self) -> None:
        return None


class CompletedGenerator:
    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        progress_reporter=None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> None:
        return None


class FakeSeriesKnowledgeMemoryRefresher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def refresh(self, series_id: str, video_id: str) -> None:
        self.calls.append((series_id, video_id))


class FailingSeriesKnowledgeMemoryRefresher:
    def refresh(self, series_id: str, video_id: str) -> None:
        del video_id
        raise RuntimeError(f"refresh failed for {series_id}")


class FakeIndexRefresher:
    def __init__(self) -> None:
        self.refresh_calls = 0
        self.video_upserts: list[tuple[str, str]] = []
        self.video_deletes: list[tuple[str, str]] = []
        self.series_deletes: list[str] = []

    def refresh(self) -> None:
        self.refresh_calls += 1

    def refresh_all(self) -> None:
        self.refresh_calls += 1

    def upsert_video(self, series_id: str, video_id: str) -> None:
        self.video_upserts.append((series_id, video_id))

    def delete_video(self, series_id: str, video_id: str) -> None:
        self.video_deletes.append((series_id, video_id))

    def delete_series(self, series_id: str) -> None:
        self.series_deletes.append(series_id)


class FakeGenerationActivityChecker:
    def __init__(
        self,
        *,
        active_videos: set[tuple[str, str]] | None = None,
        active_series: set[str] | None = None,
    ) -> None:
        self._active_videos = active_videos or set()
        self._active_series = active_series or set()

    def is_video_generation_active(self, series_id: str, video_id: str) -> bool:
        return (series_id, video_id) in self._active_videos

    def is_series_generation_active(self, series_id: str) -> bool:
        return series_id in self._active_series


class FakeImportWorkspace:
    def import_local_series(self, *, title: str, files: list[tuple[str, object]]):
        del files
        return LibrarySeriesDTO(id="series-1", title=title, videos=[])

    def import_local_playground_videos(self, *, files: list[tuple[str, object]]):
        del files
        return []

    def import_local_series_videos(self, *, series_id: str, files: list[tuple[str, object]]):
        del series_id, files
        return []


class FakeMutationWorkspace:
    def __init__(self) -> None:
        self.deleted_videos: list[tuple[str, str]] = []
        self.deleted_series: list[str] = []
        self._series = [
            LibrarySeriesDTO(
                id="series-1",
                title="Series 1",
                videos=[
                    LibraryVideoCardDTO(id="video-processed", title="Processed", source_name="p.mp4", processed=True, status="ready"),
                    LibraryVideoCardDTO(id="video-unprocessed", title="Pending", source_name="u.mp4", processed=False, status="pending"),
                ],
            ),
            LibrarySeriesDTO(
                id="series-2",
                title="Series 2",
                videos=[
                    LibraryVideoCardDTO(id="video-only-unprocessed", title="Pending", source_name="u2.mp4", processed=False, status="pending"),
                ],
            ),
        ]

    def list_series(self):
        return self._series

    def get_video_source(self, series_id: str, video_id: str):
        for series in self._series:
            if series.id != series_id:
                continue
            for video in series.videos:
                if video.id == video_id:
                    return type("Source", (), {"processed": video.processed})()
        return None

    def delete_video(self, series_id: str, video_id: str) -> bool:
        for series in self._series:
            if series.id != series_id:
                continue
            before = len(series.videos)
            series.videos[:] = [video for video in series.videos if video.id != video_id]
            deleted = len(series.videos) != before
            if deleted:
                self.deleted_videos.append((series_id, video_id))
            return deleted
        return False

    def delete_series(self, series_id: str) -> bool:
        before = len(self._series)
        self._series = [series for series in self._series if series.id != series_id]
        deleted = len(self._series) != before
        if deleted:
            self.deleted_series.append(series_id)
        return deleted


class MutableRetrievalWorkspace:
    def __init__(self) -> None:
        self._workspace = WorkspaceDTO(id="workspace", title="Workspace")
        self._series = [
            LibrarySeriesDTO(
                id="series-1",
                title="Series 1",
                videos=[
                    LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=True, status="ready"),
                    LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=True, status="ready"),
                ],
            ),
            LibrarySeriesDTO(
                id="series-2",
                title="Series 2",
                videos=[
                    LibraryVideoCardDTO(id="video-3", title="Video 3", source_name="video-3.mp4", processed=True, status="ready"),
                ],
            ),
        ]
        self._summaries = {
            ("series-1", "video-1"): VideoSummaryDTO(
                series_id="series-1",
                video_id="video-1",
                title="Video 1",
                summary={"title": "Video 1", "one_sentence_summary": "概况一", "core_problem": "", "chapters": [], "key_takeaways": []},
            ),
            ("series-1", "video-2"): VideoSummaryDTO(
                series_id="series-1",
                video_id="video-2",
                title="Video 2",
                summary={"title": "Video 2", "one_sentence_summary": "概况二", "core_problem": "", "chapters": [], "key_takeaways": []},
            ),
            ("series-2", "video-3"): VideoSummaryDTO(
                series_id="series-2",
                video_id="video-3",
                title="Video 3",
                summary={"title": "Video 3", "one_sentence_summary": "概况三", "core_problem": "", "chapters": [], "key_takeaways": []},
            ),
        }
        self._transcripts = {
            ("series-1", "video-1"): VideoTranscriptDTO(
                series_id="series-1",
                video_id="video-1",
                title="Video 1",
                duration_seconds=10.0,
                segments=[type("Seg", (), {"start_seconds": 0.0, "end_seconds": 5.0, "text": "视频一转写"})()],
            ),
            ("series-1", "video-2"): VideoTranscriptDTO(
                series_id="series-1",
                video_id="video-2",
                title="Video 2",
                duration_seconds=10.0,
                segments=[type("Seg", (), {"start_seconds": 5.0, "end_seconds": 10.0, "text": "视频二转写"})()],
            ),
            ("series-2", "video-3"): VideoTranscriptDTO(
                series_id="series-2",
                video_id="video-3",
                title="Video 3",
                duration_seconds=8.0,
                segments=[type("Seg", (), {"start_seconds": 0.0, "end_seconds": 4.0, "text": "视频三转写"})()],
            ),
        }

    def get_workspace(self) -> WorkspaceDTO:
        return self._workspace

    def list_series(self) -> list[LibrarySeriesDTO]:
        return self._series

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        return self._summaries.get((series_id, video_id))

    def get_video_transcript(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        return self._transcripts.get((series_id, video_id))

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        del series_id, video_id
        return None

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        del series_id, video_id
        return None

    def get_video_workspace_tools(self, series_id: str, video_id: str):
        del series_id, video_id
        return None

    def update_video_summary_text(self, series_id: str, video_id: str, new_text: str) -> None:
        current = self._summaries[(series_id, video_id)]
        self._summaries[(series_id, video_id)] = VideoSummaryDTO(
            series_id=current.series_id,
            video_id=current.video_id,
            title=current.title,
            summary={
                **current.summary,
                "one_sentence_summary": new_text,
            },
        )

    def add_pending_series(self, series_id: str) -> None:
        self._series.append(
            LibrarySeriesDTO(
                id=series_id,
                title=series_id,
                videos=[
                    LibraryVideoCardDTO(
                        id="pending-video",
                        title="Pending Video",
                        source_name="pending.mp4",
                        processed=False,
                        status="pending",
                    )
                ],
            )
        )


class FakeKnowledgeCardWorkspace:
    def __init__(self) -> None:
        self._cards = VideoKnowledgeCardsDTO(series_id="series-1", video_id="video-1", title="Video 1", cards=[])

    def get_video_source(self, series_id: str, video_id: str):
        return object() if (series_id, video_id) == ("series-1", "video-1") else None

    def get_video_summary(self, series_id: str, video_id: str):
        if (series_id, video_id) != ("series-1", "video-1"):
            return None
        return VideoSummaryDTO(
            series_id="series-1",
            video_id="video-1",
            title="Video 1",
            summary={"title": "Video 1", "one_sentence_summary": "概况一", "chapters": [], "key_takeaways": []},
        )

    def save_video_knowledge_cards(self, series_id: str, video_id: str, *, title: str, cards):
        self._cards = VideoKnowledgeCardsDTO(series_id=series_id, video_id=video_id, title=title, cards=cards)

    def get_video_knowledge_cards(self, series_id: str, video_id: str):
        if (series_id, video_id) != ("series-1", "video-1"):
            return None
        return self._cards


class FakeKnowledgeCardGenerator:
    def run(self, *, title: str, summary_data: dict[str, object]):
        del title, summary_data
        return []


class FakeNotesMutationWorkspace:
    def __init__(self) -> None:
        self._note = VideoNoteDTO(
            id="note-1",
            title="n1",
            content="c1",
            source="manual",
            created_at="2026-05-04T00:00:00Z",
            updated_at="2026-05-04T00:00:00Z",
        )

    def create_video_note(self, series_id: str, video_id: str, *, title: str, content: str, source: str):
        del series_id, video_id, title, content, source
        return self._note

    def update_video_note(self, series_id: str, video_id: str, note_id: str, *, title: str, content: str):
        del series_id, video_id, note_id, title, content
        return self._note

    def delete_video_note(self, series_id: str, video_id: str, note_id: str):
        del series_id, video_id, note_id
        return True


def _wait_until(predicate, timeout_seconds: float = 2.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _record_upsert(tracker, executed, observed_details, series_id, video_id):
    observed_details.append(tracker.get_snapshot("agent-memory-refresh").detail)
    executed.append((series_id, video_id))


@contextmanager
def _patched_thread_start():
    scheduled_targets: list[callable] = []

    def fake_start(thread_self):
        scheduled_targets.append(thread_self._target)

    with patch("backend.api.bootstrap.Thread.start", fake_start):
        yield scheduled_targets


if __name__ == "__main__":
    unittest.main()
