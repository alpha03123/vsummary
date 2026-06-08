from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests import _path_setup  # noqa: F401

from backend.api.app import create_app
from backend.api.bootstrap import ApiContainer
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.rag_models import RAG_EMBEDDING_REQUIRED_MESSAGE, RagModelManager


class RagModelManagerTests(unittest.TestCase):
    def test_list_models_reports_embedding_and_reranker_download_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            _write_model_marker(root_dir, "models--Qdrant--bge-small-zh-v1.5", extra_files=("model_optimized.onnx",))
            manager = RagModelManager(root_dir=root_dir, progress_tracker=InMemoryProgressTracker())

            models = manager.list_models()

            self.assertEqual([model.key for model in models], ["embedding", "reranker"])
            self.assertTrue(models[0].downloaded)
            self.assertFalse(models[1].downloaded)

    def test_partial_model_directory_is_not_reported_as_downloaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            _write_model_marker(root_dir, "models--Qdrant--bge-small-zh-v1.5")
            manager = RagModelManager(root_dir=root_dir, progress_tracker=InMemoryProgressTracker())

            models = manager.list_models()

            self.assertFalse(models[0].downloaded)

    def test_download_does_not_start_second_worker_when_model_is_already_downloading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            calls: list[str] = []
            release = threading.Event()

            def blocking_downloader(spec, reporter) -> None:
                del reporter
                calls.append(spec.key)
                release.wait(2.0)

            manager = RagModelManager(
                root_dir=root_dir,
                progress_tracker=InMemoryProgressTracker(),
                downloader=blocking_downloader,
            )

            first = manager.start_download("embedding")
            second = manager.start_download("embedding")
            release.set()

            self.assertEqual(first.status, "running")
            self.assertEqual(second.status, "running")
            self.assertEqual(calls, ["embedding"])


class RagModelAgentRouteTests(unittest.TestCase):
    def test_series_chat_requires_embedding_model_without_starting_download(self) -> None:
        rag_model_manager = FakeMissingEmbeddingRagModelManager()
        container = FakeContainer(rag_model_manager=rag_model_manager)
        client = TestClient(create_app(container))

        response = client.post(
            "/api/agent/chat",
            json={
                "session_id": "series|series-1|series-home",
                "message": "这个系列讲了啥",
                "context": {"scope_type": "series", "series_id": "series-1"},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assistant_message"], RAG_EMBEDDING_REQUIRED_MESSAGE)
        self.assertFalse(container.graph_service_called)
        self.assertFalse(rag_model_manager.start_download_called)

    def test_series_chat_returns_download_message_while_rag_model_is_downloading(self) -> None:
        container = FakeContainer(rag_model_manager=FakeDownloadingRagModelManager())
        client = TestClient(create_app(container))

        response = client.post(
            "/api/agent/chat",
            json={
                "session_id": "series|series-1|series-home",
                "message": "这期视频讲了啥",
                "context": {"scope_type": "series", "series_id": "series-1"},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assistant_message"], "正在下载 RAG 模型，请等待下载完成后再提问。")
        self.assertFalse(container.graph_service_called)

    def test_clear_session_does_not_initialize_graph_while_rag_model_is_downloading(self) -> None:
        session_store = FakeSessionStore()
        container = FakeContainer(
            rag_model_manager=FakeDownloadingRagModelManager(),
            agent_session_store=session_store,
        )
        client = TestClient(create_app(container))

        response = client.post(
            "/api/agent/session/clear",
            json={
                "session_id": "series|series-1|series-home",
                "context": {"scope_type": "series", "series_id": "series-1"},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(session_store.cleared_session_ids, ["series|series-1|series-home"])
        self.assertFalse(container.graph_service_called)


class FakeDownloadingRagModelManager:
    def has_active_download(self) -> bool:
        return True

    def is_downloaded(self, key: str) -> bool:
        return key == "embedding"


class FakeMissingEmbeddingRagModelManager:
    def __init__(self) -> None:
        self.start_download_called = False

    def has_active_download(self) -> bool:
        return False

    def is_downloaded(self, key: str) -> bool:
        return False

    def start_download(self, key: str) -> None:
        del key
        self.start_download_called = True


class FakeContainer:
    def __init__(self, *, rag_model_manager, agent_session_store=None) -> None:
        self.root_dir = Path.cwd()
        self.config_path = self.root_dir / "config" / "settings.toml"
        self.rag_model_manager = rag_model_manager
        self.agent_session_store = agent_session_store or FakeSessionStore()
        self.graph_service_called = False

    def get_agent_graph_service(self):
        self.graph_service_called = True
        raise AssertionError("series chat should be blocked during RAG model download")


class FakeSessionStore:
    def __init__(self) -> None:
        self.cleared_session_ids: list[str] = []

    def clear_snapshot(self, session_id: str) -> None:
        self.cleared_session_ids.append(session_id)


def _write_model_marker(root_dir: Path, model_dir_name: str, extra_files: tuple[str, ...] = ()) -> None:
    model_dir = root_dir / "data" / "models" / "fastembed" / model_dir_name
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    for file_name in extra_files:
        (model_dir / file_name).write_text("{}", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
