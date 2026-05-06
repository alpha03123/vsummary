from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import Callable

from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.infrastructure.huggingface_model_downloader import (
    HuggingFaceDownloadSpec,
    HuggingFaceModelDownloader,
)
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.settings import load_env_settings


RAG_MODEL_DOWNLOAD_MESSAGE = "正在下载 RAG 模型，请等待下载完成后再提问。"
RAG_EMBEDDING_REQUIRED_MESSAGE = "向量检索模型尚未下载，请先到设置中下载 RAG 向量模型后再使用系列问答。"
RAG_RERANKER_REQUIRED_MESSAGE = "重排序模型尚未下载，请先到设置中下载后再开启重排序。"


@dataclass(frozen=True)
class RagModelSpec:
    key: str
    label: str
    repo_id: str
    local_dir_name: str
    purpose: str
    required_files: tuple[str, ...]


@dataclass(frozen=True)
class RagModelStatus:
    key: str
    label: str
    repo_id: str
    local_path: str
    purpose: str
    downloaded: bool
    status: str
    progress: float | None
    detail: str | None
    error: str | None


RAG_MODEL_SPECS: dict[str, RagModelSpec] = {
    "embedding": RagModelSpec(
        key="embedding",
        label="bge-base-zh-v1.5(embedding)",
        repo_id="BAAI/bge-base-zh-v1.5",
        local_dir_name="bge-base-zh-v1.5",
        purpose="向量化检索候选内容",
        required_files=("config.json", "modules.json"),
    ),
    "reranker": RagModelSpec(
        key="reranker",
        label="bge-reranker-v2-m3(reranker)",
        repo_id="BAAI/bge-reranker-v2-m3",
        local_dir_name="bge-reranker-v2-m3",
        purpose="对检索候选内容进行重排序",
        required_files=("config.json",),
    ),
}


class RagModelManager:
    def __init__(
        self,
        *,
        root_dir: Path,
        progress_tracker: InMemoryProgressTracker,
        downloader: Callable[[RagModelSpec, ProgressReporter], None] | None = None,
    ) -> None:
        self._root_dir = root_dir
        self._models_root = root_dir / "data" / "models" / "huggingface"
        self._progress_tracker = progress_tracker
        self._downloader = downloader or self._download_from_huggingface
        self._hf_downloader = HuggingFaceModelDownloader()
        self._lock = Lock()
        self._active_keys: set[str] = set()

    def list_models(self) -> list[RagModelStatus]:
        return [self.get_status(key) for key in RAG_MODEL_SPECS]

    @property
    def progress_tracker(self) -> InMemoryProgressTracker:
        return self._progress_tracker

    def get_status(self, key: str) -> RagModelStatus:
        spec = self._get_spec(key)
        snapshot = self._progress_tracker.get_snapshot(self._task_id(spec.key))
        return RagModelStatus(
            key=spec.key,
            label=spec.label,
            repo_id=spec.repo_id,
            local_path=str(self.local_model_dir(spec.key)),
            purpose=spec.purpose,
            downloaded=self.is_downloaded(spec.key),
            status=snapshot.status,
            progress=snapshot.progress,
            detail=snapshot.detail,
            error=snapshot.error,
        )

    def start_download(self, key: str) -> RagModelStatus:
        spec = self._get_spec(key)
        if self.is_downloaded(spec.key):
            return self.get_status(spec.key)
        with self._lock:
            if spec.key in self._active_keys:
                return self.get_status(spec.key)
            snapshot = self._progress_tracker.get_snapshot(self._task_id(spec.key))
            if snapshot.status in {"running", "cancelling"}:
                return self.get_status(spec.key)
            self._active_keys.add(spec.key)
            reporter = self._progress_tracker.create_reporter(self._task_id(spec.key))
            reporter.update("download", 0.0, f"正在下载 RAG 模型：{spec.label}")
        Thread(target=self._run_download, args=(spec, reporter), daemon=True).start()
        return self.get_status(spec.key)

    def cancel_download(self, key: str) -> RagModelStatus:
        spec = self._get_spec(key)
        self._progress_tracker.request_cancel(self._task_id(spec.key))
        return self.get_status(spec.key)

    def has_active_download(self) -> bool:
        with self._lock:
            if self._active_keys:
                return True
        return any(
            self._progress_tracker.get_snapshot(self._task_id(key)).status == "running"
            for key in RAG_MODEL_SPECS
        )

    def all_downloaded(self) -> bool:
        return all(self.is_downloaded(key) for key in RAG_MODEL_SPECS)

    def is_downloaded(self, key: str) -> bool:
        spec = self._get_spec(key)
        model_dir = self.local_model_dir(key)
        if not model_dir.is_dir():
            return False
        if not all((model_dir / file_name).is_file() for file_name in spec.required_files):
            return False
        return any(model_dir.glob("*.safetensors")) or any(model_dir.glob("*.bin"))

    def local_model_dir(self, key: str) -> Path:
        spec = self._get_spec(key)
        return self._models_root / spec.local_dir_name

    def _run_download(self, spec: RagModelSpec, reporter: ProgressReporter) -> None:
        try:
            self._downloader(spec, reporter)
            reporter.completed(f"RAG 模型已下载：{spec.label}")
        except Exception as error:
            if "取消" in str(error) or "cancel" in str(error).lower():
                reporter.cancelled("RAG 模型下载已取消")
                return
            reporter.failed(str(error))
        finally:
            with self._lock:
                self._active_keys.discard(spec.key)

    def _download_from_huggingface(self, spec: RagModelSpec, reporter: ProgressReporter) -> None:
        env_settings = load_env_settings(self._root_dir)
        endpoint = env_settings.hf_endpoint.strip() or None
        self._hf_downloader.download(
            HuggingFaceDownloadSpec(
                repo_id=spec.repo_id,
                target_dir=self.local_model_dir(spec.key),
                required_files=spec.required_files,
                required_file_patterns=("*.safetensors", "*.bin"),
                allow_patterns=(),
                endpoint=endpoint,
            ),
            reporter,
        )
        reporter.update("validate", 95.0, f"正在校验 RAG 模型：{spec.label}")

    def stream_task_id(self, key: str) -> str:
        spec = self._get_spec(key)
        return self._task_id(spec.key)

    def _get_spec(self, key: str) -> RagModelSpec:
        normalized = key.strip().lower()
        if normalized not in RAG_MODEL_SPECS:
            raise ValueError(f"unsupported RAG model '{key}'")
        return RAG_MODEL_SPECS[normalized]

    @staticmethod
    def _task_id(key: str) -> str:
        return f"rag-model-download/{key}"
