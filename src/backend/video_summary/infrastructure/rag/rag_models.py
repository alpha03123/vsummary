"""RAG 系列问答所需的本地模型（embedding / reranker）的元数据与下载管理。

业务目的：让 Agent RAG（`SeriesRetrievalService`）所需的 fastembed 模型具备
"是否已下载 / 当前进度 / 主动下载"等可视化能力，并把 fastembed 的目录命名
约定集中到一处，避免上层业务感知快照来源差异。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Literal

from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.config.settings import apply_runtime_env_overrides


RAG_MODEL_DOWNLOAD_MESSAGE = "正在下载 RAG 模型，请等待下载完成后再提问。"
RAG_EMBEDDING_REQUIRED_MESSAGE = "向量检索模型尚未下载，请先到设置中下载 RAG 向量模型后再使用系列问答。"
RAG_RERANKER_REQUIRED_MESSAGE = "重排序模型尚未下载，请先到设置中下载后再开启重排序。"


@dataclass(frozen=True)
class RagModelSpec:
    """单个 RAG 模型的元信息（用于 UI 展示与下载器选型）。

    Attributes:
        key: 业务键（`embedding` / `reranker`）。
        label: 面向用户的中文显示名。
        model_name: FastEmbed / HuggingFace 仓库 ID。
        model_kind: 模型用途，取值 `embedding` 或 `reranker`。
        purpose: 人类可读的一句话用途说明（用于设置页 / 前端展示）。
    """

    key: str
    label: str
    model_name: str
    model_kind: Literal["embedding", "reranker"]
    purpose: str


@dataclass(frozen=True)
class RagModelStatus:
    """单条 RAG 模型在前端的展示快照。

    Attributes:
        key: 与 `RagModelSpec.key` 对齐。
        label: 展示名。
        repo_id: 模型仓库 ID（即 `model_name`）。
        local_path: 当前选定的本地缓存目录。
        purpose: 用途描述。
        downloaded: 是否已完整下载到本地。
        status: 当前下载/校验阶段（`idle` / `running` / `completed` / `failed` 等）。
        progress: 进度百分比，区间 `[0, 100]`。
        detail: 人类可读的当前阶段描述。
        error: 失败原因消息；非 `failed` 时为 `None`。
    """

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
        label="bge-small-zh-v1.5 (FastEmbed)",
        model_name="BAAI/bge-small-zh-v1.5",
        model_kind="embedding",
        purpose="向量化检索候选内容",
    ),
    "reranker": RagModelSpec(
        key="reranker",
        label="bge-reranker-base (FastEmbed)",
        model_name="BAAI/bge-reranker-base",
        model_kind="reranker",
        purpose="对检索候选内容进行重排序",
    ),
}


class RagModelManager:
    """RAG 模型的"是否下载 / 下载进度 / 启动下载"门面。

    主要职责：
    - 暴露 `list_models` / `get_status` 给前端拉取状态；
    - 通过 `start_download` 在后台线程里下载模型，并把进度写入
      `InMemoryProgressTracker`，方便 SSE 推送；
    - 通过 `_get_fastembed_metadata` 探测 FastEmbed 实际缓存目录，
      兼容 `models--owner--name/` 与 `fast-xxx/` 两种命名。
    """

    def __init__(
        self,
        *,
        root_dir: Path,
        progress_tracker: InMemoryProgressTracker,
        downloader: Callable[[RagModelSpec, ProgressReporter], None] | None = None,
        on_download_completed: Callable[[str], None] | None = None,
    ) -> None:
        """注入项目根目录、进度跟踪器与可选的自定义下载器 / 完成回调。

        Args:
            root_dir: 项目根目录；模型缓存目录解析为 `root_dir/data/models/fastembed/`。
            progress_tracker: 用于写入下载进度并被前端 SSE 订阅的 `InMemoryProgressTracker`。
            downloader: 可选的自定义下载器；为 `None` 时使用默认的
                `_download_from_huggingface` 实现。
            on_download_completed: 下载完成后的回调（接收模型 key），
                为 `None` 时不通知。
        """
        self._root_dir = root_dir
        self._models_root = root_dir / "data" / "models" / "fastembed"
        self._progress_tracker = progress_tracker
        self._downloader = downloader or self._download_from_huggingface
        self._on_download_completed = on_download_completed
        self._lock = Lock()
        self._active_keys: set[str] = set()

    def list_models(self) -> list[RagModelStatus]:
        """枚举所有 RAG 模型的状态快照（按 `RAG_MODEL_SPECS` 注册顺序）。"""
        return [self.get_status(key) for key in RAG_MODEL_SPECS]

    @property
    def progress_tracker(self) -> InMemoryProgressTracker:
        """对外暴露底层进度跟踪器，便于上层直接订阅 SSE。"""
        return self._progress_tracker

    def get_status(self, key: str) -> RagModelStatus:
        """读取指定模型的状态快照：合并磁盘检查与进度 tracker 的最新事件。"""
        spec = self._get_spec(key)
        snapshot = self._progress_tracker.get_snapshot(self._task_id(spec.key))
        return RagModelStatus(
            key=spec.key,
            label=spec.label,
            repo_id=spec.model_name,
            local_path=str(self.local_model_dir(spec.key)),
            purpose=spec.purpose,
            downloaded=self.is_downloaded(spec.key),
            status=snapshot.status,
            progress=snapshot.progress,
            detail=snapshot.detail,
            error=snapshot.error,
        )

    def start_download(self, key: str) -> RagModelStatus:
        """在后台线程里启动一次模型下载。

        去重语义：若已下载 / 已有进行中的任务 / 进度 tracker 报 `running`，均直接
        返回当前状态而不重复触发。

        Args:
            key: 业务键（`embedding` / `reranker`）。

        Returns:
            下载触发后（或被去重后）的当前状态快照。
        """
        spec = self._get_spec(key)
        if self.is_downloaded(spec.key):
            return self.get_status(spec.key)
        with self._lock:
            if spec.key in self._active_keys:
                return self.get_status(spec.key)
            snapshot = self._progress_tracker.get_snapshot(self._task_id(spec.key))
            if snapshot.status == "running":
                return self.get_status(spec.key)
            self._active_keys.add(spec.key)
            reporter = self._progress_tracker.create_reporter(self._task_id(spec.key))
            reporter.update("download", 0.0, f"正在下载 RAG 模型：{spec.label}")
        Thread(target=self._run_download, args=(spec, reporter), daemon=True).start()
        return self.get_status(spec.key)

    def has_active_download(self) -> bool:
        """判断是否存在进行中的下载（同时检查本地活动集合与 tracker 状态）。"""
        with self._lock:
            if self._active_keys:
                return True
        return any(
            self._progress_tracker.get_snapshot(self._task_id(key)).status == "running"
            for key in RAG_MODEL_SPECS
        )

    def all_downloaded(self) -> bool:
        """所有 RAG 模型是否都已下载完成。"""
        return all(self.is_downloaded(key) for key in RAG_MODEL_SPECS)

    def is_downloaded(self, key: str) -> bool:
        """判断指定模型是否已在本地某个候选目录里具备 `model_file`。"""
        spec = self._get_spec(key)
        metadata = self._get_fastembed_metadata(spec)
        model_file = _metadata_model_file(metadata)
        return any(
            _has_required_file(model_dir, model_file)
            for model_dir in self._candidate_model_dirs(spec, metadata)
        )

    def local_model_dir(self, key: str) -> Path:
        """返回指定模型应使用的本地目录：优先挑已有 `model_file` 的候选目录。

        若全部候选目录均无 `model_file`，回退到第一个候选目录（供 FastEmbed 写入）。
        """
        spec = self._get_spec(key)
        metadata = self._get_fastembed_metadata(spec)
        model_file = _metadata_model_file(metadata)
        candidates = self._candidate_model_dirs(spec, metadata)
        for model_dir in candidates:
            if _has_required_file(model_dir, model_file):
                return model_dir
        for model_dir in candidates:
            if model_dir.is_dir():
                return model_dir
        return candidates[0]

    def _run_download(self, spec: RagModelSpec, reporter: ProgressReporter) -> None:
        """后台线程的下载主循环：调用注入的下载器，校验完成后通知回调。"""
        try:
            self._downloader(spec, reporter)
            if not self.is_downloaded(spec.key):
                raise RuntimeError(f"RAG 模型下载后校验失败：{spec.label}")
            reporter.completed(f"RAG 模型已下载：{spec.label}")
            if self._on_download_completed is not None:
                self._on_download_completed(spec.key)
        except Exception as error:
            reporter.failed(str(error))
        finally:
            with self._lock:
                self._active_keys.discard(spec.key)

    def _download_from_huggingface(self, spec: RagModelSpec, reporter: ProgressReporter) -> None:
        """默认下载实现：实例化 FastEmbed 的 `TextEmbedding` / `TextCrossEncoder`。

        FastEmbed 在首次构造时会按 `cache_dir` 自动从 HuggingFace 下载模型；
        这里不直接调 huggingface_hub，是为了与 fastembed 自身的缓存格式保持一致。
        """
        apply_runtime_env_overrides(self._root_dir)
        reporter.update("download", 5.0, f"正在下载模型文件：{spec.model_name}")
        if spec.model_kind == "embedding":
            from fastembed import TextEmbedding

            TextEmbedding(model_name=spec.model_name, cache_dir=str(self._models_root))
        elif spec.model_kind == "reranker":
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            TextCrossEncoder(model_name=spec.model_name, cache_dir=str(self._models_root))
        else:
            raise ValueError(f"unsupported RAG model '{spec.key}'")
        reporter.update("validate", 95.0, f"正在校验 RAG 模型：{spec.label}")

    def stream_task_id(self, key: str) -> str:
        """返回该模型在进度 tracker 中对应的任务 ID（供 SSE 端点订阅）。"""
        spec = self._get_spec(key)
        return self._task_id(spec.key)

    def _get_spec(self, key: str) -> RagModelSpec:
        """按 key（大小写不敏感）查找 `RagModelSpec`；找不到时抛 `ValueError`。"""
        normalized = key.strip().lower()
        if normalized not in RAG_MODEL_SPECS:
            raise ValueError(f"unsupported RAG model '{key}'")
        return RAG_MODEL_SPECS[normalized]

    def _get_fastembed_metadata(self, spec: RagModelSpec) -> dict:
        """从 FastEmbed 的 `list_supported_models()` 中找出当前模型对应的元数据。"""
        if spec.model_kind == "embedding":
            from fastembed import TextEmbedding

            models = TextEmbedding.list_supported_models()
        elif spec.model_kind == "reranker":
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            models = TextCrossEncoder.list_supported_models()
        else:
            raise ValueError(f"unsupported RAG model '{spec.key}'")
        for model in models:
            if str(model.get("model", "")).lower() == spec.model_name.lower():
                return model
        raise RuntimeError(f"当前 FastEmbed 不支持 RAG 模型：{spec.model_name}")

    def _candidate_model_dirs(self, spec: RagModelSpec, metadata: dict) -> list[Path]:
        """根据 FastEmbed 元数据推导候选缓存目录列表。

        - `sources.hf`：HuggingFace 缓存样式 `models--owner--name/`；
        - `sources.url`：tarball 缓存样式 `fast-<basename>/` 或 `<basename>/`。
        """
        sources = metadata.get("sources")
        if not isinstance(sources, dict):
            raise RuntimeError(f"FastEmbed 模型元数据缺少 sources：{spec.model_name}")

        candidates: list[Path] = []
        hf_source = sources.get("hf")
        if isinstance(hf_source, str) and hf_source.strip():
            candidates.append(self._models_root / f"models--{hf_source.strip().replace('/', '--')}")

        url_source = sources.get("url")
        if isinstance(url_source, str) and url_source.strip():
            model_basename = spec.model_name.split("/")[-1]
            prefix = "fast-" if bool(sources.get("_deprecated_tar_struct")) else ""
            candidates.append(self._models_root / f"{prefix}{model_basename}")

        if not candidates:
            raise RuntimeError(f"FastEmbed 模型元数据缺少可用缓存来源：{spec.model_name}")
        return candidates

    @staticmethod
    def _task_id(key: str) -> str:
        """生成进度 tracker 中的 task_id：`rag-model-download/<key>`。"""
        return f"rag-model-download/{key}"


def _has_required_file(model_dir: Path, file_name: str) -> bool:
    """判断指定目录下是否存在 `file_name`（直接存在或子路径以它结尾）。"""
    if not model_dir.is_dir():
        return False
    direct_path = model_dir / file_name
    if direct_path.is_file():
        return True
    normalized = file_name.replace("\\", "/")
    return any(path.is_file() and path.as_posix().endswith(normalized) for path in model_dir.rglob(Path(file_name).name))


def _metadata_model_file(metadata: dict) -> str:
    """从 FastEmbed 模型元数据中读取关键 `model_file` 字段（缺失时抛 `RuntimeError`）。"""
    model_file = metadata.get("model_file")
    if not isinstance(model_file, str) or not model_file.strip():
        raise RuntimeError("FastEmbed 模型元数据缺少 model_file。")
    return model_file.strip()
