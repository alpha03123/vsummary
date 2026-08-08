from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from tests import _path_setup  # noqa: F401

from backend.api.http.app import create_app
from backend.api.di.bootstrap import ApiContainer
from backend.video_summary.infrastructure.asr.huggingface_model_downloader import (
    HuggingFaceCacheWarmSpec,
    HuggingFaceDownloadCancelled,
    _raise_if_download_cancelled,
)
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.rag.rag_models import (
    _FASTEMBED_BASE_ALLOW_PATTERNS,
    RAG_EMBEDDING_REQUIRED_MESSAGE,
    RagModelManager,
)


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

    def test_list_models_accepts_fastembed_url_cache_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            _write_model_marker(root_dir, "fast-bge-small-zh-v1.5", extra_files=("model_optimized.onnx",))
            manager = RagModelManager(root_dir=root_dir, progress_tracker=InMemoryProgressTracker())

            models = manager.list_models()

            self.assertTrue(models[0].downloaded)
            self.assertTrue(models[0].local_path.endswith("fast-bge-small-zh-v1.5"))

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

    def test_download_fails_when_fastembed_cache_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            completed: list[str] = []

            def no_op_downloader(spec, reporter) -> None:
                del spec, reporter

            manager = RagModelManager(
                root_dir=root_dir,
                progress_tracker=InMemoryProgressTracker(),
                downloader=no_op_downloader,
                on_download_completed=completed.append,
            )

            manager.start_download("embedding")
            _wait_until(lambda: not manager.has_active_download())
            snapshot = manager.progress_tracker.get_snapshot(manager.stream_task_id("embedding"))

            self.assertEqual(snapshot.status, "failed")
            self.assertIn("RAG 模型下载后校验失败", snapshot.error or "")
            self.assertEqual(completed, [])

    def test_failed_download_preserves_hf_cache_for_resume_but_clears_lock_directory(self) -> None:
        """失败时 HF 缓存目录必须保留：里面的半成品 blob 是下次续传的锚点。

        锁目录仍然要清掉——它不含数据，残留会挡住下一次下载。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            model_dir = root_dir / "data" / "models" / "fastembed" / "models--Qdrant--bge-small-zh-v1.5"
            blob_dir = model_dir / "blobs"
            lock_dir = root_dir / "data" / "models" / "fastembed" / ".locks" / "models--Qdrant--bge-small-zh-v1.5"
            unrelated_lock_dir = root_dir / "data" / "models" / "fastembed" / ".locks" / "models--BAAI--bge-reranker-base"
            unrelated_lock_dir.mkdir(parents=True)
            (unrelated_lock_dir / "keep.lock").write_text("", encoding="utf-8")

            def failing_downloader(spec, reporter) -> None:
                del spec, reporter
                blob_dir.mkdir(parents=True)
                (blob_dir / "abc123.incomplete").write_bytes(b"partial-bytes")
                lock_dir.mkdir(parents=True)
                (lock_dir / "download.lock").write_text("", encoding="utf-8")
                raise RuntimeError("network failed")

            manager = RagModelManager(
                root_dir=root_dir,
                progress_tracker=InMemoryProgressTracker(),
                downloader=failing_downloader,
            )

            manager.start_download("embedding")
            _wait_until(lambda: not manager.has_active_download())
            snapshot = manager.progress_tracker.get_snapshot(manager.stream_task_id("embedding"))

            self.assertEqual(snapshot.status, "failed")
            self.assertIn("network failed", snapshot.error or "")
            self.assertTrue((blob_dir / "abc123.incomplete").is_file())
            self.assertEqual((blob_dir / "abc123.incomplete").read_bytes(), b"partial-bytes")
            self.assertFalse(manager.is_downloaded("embedding"))
            self.assertFalse(lock_dir.exists())
            self.assertTrue(unrelated_lock_dir.exists())

    def test_failed_download_still_cleans_legacy_tarball_cache_layout(self) -> None:
        """tarball 布局（`fast-xxx/`）没有 blob 续传机制，半成品仍应删除。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            legacy_dir = root_dir / "data" / "models" / "fastembed" / "fast-bge-small-zh-v1.5"

            def failing_downloader(spec, reporter) -> None:
                del spec, reporter
                legacy_dir.mkdir(parents=True)
                (legacy_dir / "config.json").write_text("{}", encoding="utf-8")
                raise RuntimeError("network failed")

            manager = RagModelManager(
                root_dir=root_dir,
                progress_tracker=InMemoryProgressTracker(),
                downloader=failing_downloader,
            )

            manager.start_download("embedding")
            _wait_until(lambda: not manager.has_active_download())

            self.assertFalse(legacy_dir.exists())

    def test_download_start_preserves_stale_hf_cache_but_clears_stale_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            stale_model_dir = root_dir / "data" / "models" / "fastembed" / "models--Qdrant--bge-small-zh-v1.5"
            stale_lock_dir = root_dir / "data" / "models" / "fastembed" / ".locks" / "models--Qdrant--bge-small-zh-v1.5"
            stale_blob = stale_model_dir / "blobs" / "abc123.incomplete"
            stale_blob.parent.mkdir(parents=True)
            stale_blob.write_bytes(b"partial-bytes")
            stale_lock_dir.mkdir(parents=True)
            (stale_lock_dir / "download.lock").write_text("", encoding="utf-8")

            def retry_downloader(spec, reporter) -> None:
                del spec, reporter
                self.assertTrue(stale_blob.is_file())
                self.assertFalse(stale_lock_dir.exists())
                _write_model_marker(root_dir, "models--Qdrant--bge-small-zh-v1.5", extra_files=("model_optimized.onnx",))

            manager = RagModelManager(
                root_dir=root_dir,
                progress_tracker=InMemoryProgressTracker(),
                downloader=retry_downloader,
            )

            manager.start_download("embedding")
            _wait_until(lambda: not manager.has_active_download())
            snapshot = manager.progress_tracker.get_snapshot(manager.stream_task_id("embedding"))

            self.assertEqual(snapshot.status, "completed")
            self.assertTrue(manager.is_downloaded("embedding"))

    def test_prewarm_uses_sources_hf_repo_id_not_model_name(self) -> None:
        """预热必须用 `sources.hf`（`Qdrant/...`）而不是 `model_name`（`BAAI/...`）。

        两者不同：ONNX 权重托管在 Qdrant 的镜像仓库下，用 `model_name` 去预热会
        下到错误的仓库或直接 404。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            recorder = _RecordingModelDownloader(
                on_warm=lambda: _write_model_marker(
                    root_dir,
                    "models--Qdrant--bge-small-zh-v1.5",
                    extra_files=("model_optimized.onnx",),
                )
            )
            manager = RagModelManager(
                root_dir=root_dir,
                progress_tracker=InMemoryProgressTracker(),
                model_downloader=recorder,
            )

            with mock.patch.dict(os.environ, {"HF_ENDPOINT": "https://hf-mirror.com"}):
                manager.start_download("embedding")
                _wait_until(lambda: not manager.has_active_download())

            snapshot = manager.progress_tracker.get_snapshot(manager.stream_task_id("embedding"))
            self.assertEqual(snapshot.status, "completed", snapshot.error)
            self.assertEqual(len(recorder.specs), 1)

            warm_spec = recorder.specs[0]
            self.assertEqual(warm_spec.repo_id, "Qdrant/bge-small-zh-v1.5")
            self.assertNotEqual(warm_spec.repo_id, "BAAI/bge-small-zh-v1.5")
            self.assertEqual(warm_spec.cache_dir, root_dir / "data" / "models" / "fastembed")
            self.assertEqual(warm_spec.endpoint, "https://hf-mirror.com")
            self.assertIn("model_optimized.onnx", warm_spec.allow_patterns)

    def test_prewarm_allow_patterns_match_fastembed_base_list(self) -> None:
        """`allow_patterns` 必须逐字覆盖 fastembed 自己的 5 个固定 JSON。

        少一个都会让 fastembed 的 `local_files_only=True` 加载失败并回退到 GCS
        tarball（绕开镜像），等于白预热。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            recorder = _RecordingModelDownloader(
                on_warm=lambda: _write_model_marker(
                    root_dir,
                    "models--BAAI--bge-reranker-base",
                    extra_files=("onnx/model.onnx",),
                )
            )
            manager = RagModelManager(
                root_dir=root_dir,
                progress_tracker=InMemoryProgressTracker(),
                model_downloader=recorder,
            )

            manager.start_download("reranker")
            _wait_until(lambda: not manager.has_active_download())

            snapshot = manager.progress_tracker.get_snapshot(manager.stream_task_id("reranker"))
            self.assertEqual(snapshot.status, "completed", snapshot.error)

            warm_spec = recorder.specs[0]
            self.assertEqual(warm_spec.repo_id, "BAAI/bge-reranker-base")
            for base_pattern in _FASTEMBED_BASE_ALLOW_PATTERNS:
                self.assertIn(base_pattern, warm_spec.allow_patterns)
            self.assertGreater(len(warm_spec.allow_patterns), len(_FASTEMBED_BASE_ALLOW_PATTERNS))
            self.assertEqual(len(warm_spec.allow_patterns), len(set(warm_spec.allow_patterns)))

    def test_prewarm_reports_progress_and_reaches_completed(self) -> None:
        """预热必须经由 reporter 上报进度：这是 fastembed 自带下载完全没有的能力。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            recorder = _RecordingModelDownloader(
                on_warm=lambda: _write_model_marker(
                    root_dir,
                    "models--Qdrant--bge-small-zh-v1.5",
                    extra_files=("model_optimized.onnx",),
                ),
                report_progress=True,
            )
            manager = RagModelManager(
                root_dir=root_dir,
                progress_tracker=InMemoryProgressTracker(),
                model_downloader=recorder,
            )

            manager.start_download("embedding")
            _wait_until(lambda: not manager.has_active_download())

            snapshot = manager.progress_tracker.get_snapshot(manager.stream_task_id("embedding"))
            self.assertEqual(snapshot.status, "completed", snapshot.error)
            self.assertEqual(recorder.reported_progress, [10.0, 60.0])

    def test_cancelled_prewarm_reports_cancelled_and_keeps_resume_state(self) -> None:
        """取消不能被当成失败上报，且已下好的 blob 必须留着续传。

        `_run_download` 的 `except Exception` 会吞掉 `HuggingFaceDownloadCancelled`
        并报 `failed`，前端就会显示"下载出错"——而用户明明是自己点的取消。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            blob = root_dir / "data" / "models" / "fastembed" / "models--Qdrant--bge-small-zh-v1.5" / "blobs" / "abc.incomplete"

            def cancel_midway() -> None:
                blob.parent.mkdir(parents=True, exist_ok=True)
                blob.write_bytes(b"partial-bytes")
                raise HuggingFaceDownloadCancelled("模型下载已取消")

            manager = RagModelManager(
                root_dir=root_dir,
                progress_tracker=InMemoryProgressTracker(),
                model_downloader=_RecordingModelDownloader(on_warm=cancel_midway),
            )

            manager.start_download("embedding")
            _wait_until(lambda: not manager.has_active_download())

            snapshot = manager.progress_tracker.get_snapshot(manager.stream_task_id("embedding"))
            self.assertEqual(snapshot.status, "cancelled")
            self.assertTrue(blob.is_file())
            self.assertEqual(blob.read_bytes(), b"partial-bytes")
            self.assertFalse(manager.is_downloaded("embedding"))

    def test_cancel_route_drives_real_cancel_chain_to_cancelled_status(self) -> None:
        """端到端串起真实取消链路，不靠替身直接抛异常。

        覆盖 `POST /api/rag/models/{key}/download/cancel` →
        `tracker.request_cancel` → `reporter.is_cancel_requested` →
        `_raise_if_download_cancelled` → `_run_download` 上报 `cancelled`。
        上面那个用例是替身直接抛 `HuggingFaceDownloadCancelled`，
        并不能证明取消标志真的能传导进下载循环。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            entered = threading.Event()

            class _BlockingDownloader:
                def warm_cache(self, spec, reporter) -> Path:
                    del spec
                    entered.set()
                    # 模拟"逐文件下载"循环：每轮用生产代码的取消点检做检查。
                    for _ in range(200):
                        _raise_if_download_cancelled(reporter)
                        time.sleep(0.01)
                    raise AssertionError("cancel flag never reached the download loop")

            manager = RagModelManager(
                root_dir=root_dir,
                progress_tracker=InMemoryProgressTracker(),
                model_downloader=_BlockingDownloader(),
            )
            client = TestClient(create_app(FakeContainer(rag_model_manager=manager)))

            manager.start_download("embedding")
            self.assertTrue(entered.wait(2.0), "downloader never started")

            response = client.post("/api/rag/models/embedding/download/cancel")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "cancelling")
            _wait_until(lambda: not manager.has_active_download())
            snapshot = manager.progress_tracker.get_snapshot(manager.stream_task_id("embedding"))
            self.assertEqual(snapshot.status, "cancelled", snapshot.error)

    def test_cancel_route_rejects_unknown_model_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RagModelManager(
                root_dir=Path(temp_dir),
                progress_tracker=InMemoryProgressTracker(),
            )
            client = TestClient(create_app(FakeContainer(rag_model_manager=manager)))

            response = client.post("/api/rag/models/nope/download/cancel")

            self.assertEqual(response.status_code, 400)


class _RecordingModelDownloader:
    """`HuggingFaceModelDownloader` 的测试替身，只记录 `warm_cache` 的入参。

    只替换"真正下字节"的那一层，仓库 ID 推导与 `allow_patterns` 拼装仍走真实代码，
    因此这些断言校验的是生产逻辑而不是替身自己。
    """

    def __init__(self, *, on_warm=None, report_progress: bool = False, raise_cancelled: bool = False) -> None:
        self.specs: list[HuggingFaceCacheWarmSpec] = []
        self.reported_progress: list[float] = []
        self._on_warm = on_warm
        self._report_progress = report_progress
        self._raise_cancelled = raise_cancelled

    def warm_cache(self, spec: HuggingFaceCacheWarmSpec, reporter) -> Path:
        self.specs.append(spec)
        if self._report_progress:
            for percent in (10.0, 60.0):
                self.reported_progress.append(percent)
                reporter.update("download", percent, "正在下载模型文件")
        if self._on_warm is not None:
            self._on_warm()
        if self._raise_cancelled:
            raise HuggingFaceDownloadCancelled("模型下载已取消")
        return spec.cache_dir / f"models--{spec.repo_id.replace('/', '--')}"


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
        file_path = model_dir / file_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("{}", encoding="utf-8")


def _wait_until(predicate, *, timeout_seconds: float = 2.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


class PrewarmedCacheLayoutTests(unittest.TestCase):
    """预热产出的目录布局必须能被 fastembed 的离线探测命中。

    这是整条 RAG 预热设计的地基：fastembed 的 `download_model()` 第一步就是
    `snapshot_download(local_files_only=True)`，命中则直接返回、永不触网，也永不
    降级到 GCS。若布局不被识别，预热就是白做——因此这条契约必须有测试锁住，
    而不是只靠读源码得出的结论。
    """

    def test_hf_cache_layout_resolves_offline_via_snapshot_download(self) -> None:
        from huggingface_hub import snapshot_download

        commit_hash = "0" * 40
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            repo_dir = cache_dir / "models--Qdrant--bge-small-zh-v1.5"
            # 复刻 hf_hub_download(cache_dir=...) 的落盘形态：refs/<revision> 存
            # commit hash，实际文件在 snapshots/<hash>/ 下。
            (repo_dir / "refs").mkdir(parents=True)
            (repo_dir / "refs" / "main").write_text(commit_hash, encoding="utf-8")
            snapshot_dir = repo_dir / "snapshots" / commit_hash
            snapshot_dir.mkdir(parents=True)
            (snapshot_dir / "config.json").write_text("{}", encoding="utf-8")
            (snapshot_dir / "model_optimized.onnx").write_bytes(b"onnx")

            resolved = snapshot_download(
                repo_id="Qdrant/bge-small-zh-v1.5",
                cache_dir=str(cache_dir),
                local_files_only=True,
            )

            self.assertEqual(Path(resolved), snapshot_dir)
            self.assertTrue((Path(resolved) / "model_optimized.onnx").is_file())

    def test_missing_snapshot_dir_is_not_falsely_resolved(self) -> None:
        """只有 refs 没有 snapshots 时必须报错，否则会把半成品当成已就绪。"""
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import LocalEntryNotFoundError

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            repo_dir = cache_dir / "models--Qdrant--bge-small-zh-v1.5"
            (repo_dir / "refs").mkdir(parents=True)
            (repo_dir / "refs" / "main").write_text("0" * 40, encoding="utf-8")

            with self.assertRaises(LocalEntryNotFoundError):
                snapshot_download(
                    repo_id="Qdrant/bge-small-zh-v1.5",
                    cache_dir=str(cache_dir),
                    local_files_only=True,
                )


if __name__ == "__main__":
    unittest.main()
