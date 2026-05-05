from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Callable

from backend.video_summary.generation.ports import ProgressReporter
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
        self._lock = Lock()
        self._active_keys: set[str] = set()

    def list_models(self) -> list[RagModelStatus]:
        return [self.get_status(key) for key in RAG_MODEL_SPECS]

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
        from huggingface_hub import snapshot_download

        reporter.update("download", 5.0, f"正在连接模型仓库：{spec.repo_id}")
        env_settings = load_env_settings(self._root_dir)
        endpoint = env_settings.hf_endpoint.strip() or None
        total_bytes = _get_expected_download_size(spec.repo_id, endpoint=endpoint)
        tqdm_class = _build_download_tqdm_class(
            progress_reporter=reporter,
            total_bytes=total_bytes,
            label=spec.label,
        )
        reporter.raise_if_cancelled()
        self.local_model_dir(spec.key).mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=spec.repo_id,
            local_dir=self.local_model_dir(spec.key),
            endpoint=endpoint,
            max_workers=4,
            tqdm_class=tqdm_class,
        )
        reporter.raise_if_cancelled()
        reporter.update("download", 95.0, f"正在校验 RAG 模型：{spec.label}")

    def _get_spec(self, key: str) -> RagModelSpec:
        normalized = key.strip().lower()
        if normalized not in RAG_MODEL_SPECS:
            raise ValueError(f"unsupported RAG model '{key}'")
        return RAG_MODEL_SPECS[normalized]

    @staticmethod
    def _task_id(key: str) -> str:
        return f"rag-model-download/{key}"


def _get_expected_download_size(repo_id: str, *, endpoint: str | None) -> int | None:
    from huggingface_hub import HfApi

    api = HfApi(endpoint=endpoint) if endpoint else HfApi()
    try:
        info = api.model_info(repo_id, files_metadata=True)
    except Exception:
        return None
    total = 0
    has_size = False
    for sibling in info.siblings:
        size = getattr(sibling, "size", None)
        if isinstance(size, int):
            total += size
            has_size = True
    return total if has_size else None


class _DownloadProgressCoordinator:
    def __init__(self, progress_reporter: ProgressReporter, total_bytes: int | None, label: str) -> None:
        self._progress_reporter = progress_reporter
        self._total_bytes = total_bytes
        self._label = label
        self._bars: dict[int, int] = {}
        self._bar_totals: dict[int, int] = {}

    def update(self, bar: Any) -> None:
        self._progress_reporter.raise_if_cancelled()
        key = id(bar)
        current_n = int(getattr(bar, "n", 0) or 0)
        total = int(getattr(bar, "total", 0) or 0)
        if _is_byte_progress_bar(total):
            self._bars[key] = min(current_n, total)
            self._bar_totals[key] = total

        if self._total_bytes and self._total_bytes > 0 and self._bars:
            progress = min(94.0, max(5.0, (sum(self._bars.values()) / self._total_bytes) * 90.0))
        elif _is_byte_progress_bar(total):
            progress = min(94.0, max(5.0, 5.0 + (current_n / total) * 89.0))
        elif self._bar_totals:
            known_total = sum(self._bar_totals.values())
            progress = min(94.0, max(5.0, 5.0 + (sum(self._bars.values()) / known_total) * 89.0))
        else:
            progress = None

        filename = _extract_filename(getattr(bar, "desc", None))
        detail = f"正在下载 {filename}" if filename else f"正在下载 RAG 模型：{self._label}"
        self._progress_reporter.update("download", progress, detail)

    def finalize_bar(self, bar: Any) -> None:
        key = id(bar)
        total = int(getattr(bar, "total", 0) or 0)
        if _is_byte_progress_bar(total):
            self._bars[key] = total
            self._bar_totals[key] = total


def _build_download_tqdm_class(
    *,
    progress_reporter: ProgressReporter,
    total_bytes: int | None,
    label: str,
):
    from tqdm.auto import tqdm

    coordinator = _DownloadProgressCoordinator(progress_reporter, total_bytes, label)

    class DownloadProgressTqdm(tqdm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            coordinator.update(self)

        def update(self, n=1):
            result = super().update(n)
            coordinator.update(self)
            return result

        def close(self):
            coordinator.update(self)
            try:
                return super().close()
            finally:
                coordinator.finalize_bar(self)

    return DownloadProgressTqdm


def _extract_filename(desc: object) -> str | None:
    if not isinstance(desc, str):
        return None
    value = desc.strip()
    if not value:
        return None
    return value.split(":", 1)[0].strip()


def _is_byte_progress_bar(total: int) -> bool:
    return total >= 1024 * 1024
