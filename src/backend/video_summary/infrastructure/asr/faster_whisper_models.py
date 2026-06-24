"""faster-whisper 模型清单与下载管理。

提供一组预置 faster-whisper 模型 ID/标签、维护本地缓存目录，并在需要时
把模型从 HuggingFace 仓库下载到项目内的 `data/models/faster-whisper/<id>/`
目录，供 `FasterWhisperTranscriber` 离线加载。
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from backend.video_summary.infrastructure.asr.huggingface_model_downloader import (
    HuggingFaceDownloadSpec,
    HuggingFaceModelDownloader,
)
from backend.video_summary.infrastructure.config.settings import apply_runtime_env_overrides


SUPPORTED_FASTER_WHISPER_MODELS = (
    ("small", "Small"),
    ("medium", "Medium"),
    ("large-v3", "Large V3"),
    ("large-v3-turbo", "Large V3 Turbo"),
)


@dataclass(frozen=True)
class FasterWhisperModelInfo:
    """单条 faster-whisper 模型在 UI/接口层展示用的快照。

    Attributes:
        id: 模型 ID，与 faster-whisper 官方 `_MODELS` 表中的 key 对齐。
        label: 面向用户的中文/英文显示名。
        downloaded: 是否已下载到本地缓存目录。
        current: 是否与 settings 中当前配置的 `model_size` 一致。
        recommended: 是否被推荐（当前默认 `large-v3-turbo`）。
    """

    id: str
    label: str
    downloaded: bool
    current: bool
    recommended: bool


class FasterWhisperModelManager:
    """faster-whisper 模型的"目录+下载"门面。

    业务目的：让上层（设置面板、转写器装配）不必关心模型文件到底在哪个目录、
    是否已经下载好；本类负责：
    - 判定模型是否支持 / 是否已下载 / 解析本地路径或远端 ID；
    - 触发 HuggingFace 下载并把进度经由 `ProgressReporter` 上报。

    Attributes:
        models_dir: faster-whisper 模型缓存根目录（一般为
            `<root_dir>/data/models/faster-whisper`），每个模型占一个同名子目录。
    """

    def __init__(
        self,
        models_dir: Path,
        *,
        downloader: HuggingFaceModelDownloader | None = None,
    ) -> None:
        """初始化模型目录与下载器。

        Args:
            models_dir: faster-whisper 模型缓存根目录。
            downloader: 可选的 HuggingFace 下载器；为 `None` 时使用默认实现。
        """
        self._models_dir = models_dir
        self._root_dir = models_dir.parents[2]
        self._downloader = downloader or HuggingFaceModelDownloader()

    def list_models(self, current_model_size: str) -> list[FasterWhisperModelInfo]:
        """枚举支持的 faster-whisper 模型及其状态。

        Args:
            current_model_size: 当前配置中正在使用的模型 ID，用于打 `current` 标记。

        Returns:
            `FasterWhisperModelInfo` 列表，按 `SUPPORTED_FASTER_WHISPER_MODELS` 顺序排列。
        """
        return [
            FasterWhisperModelInfo(
                id=model_id,
                label=label,
                downloaded=self.is_downloaded(model_id),
                current=model_id == current_model_size,
                recommended=model_id == "large-v3-turbo",
            )
            for model_id, label in SUPPORTED_FASTER_WHISPER_MODELS
        ]

    def is_supported(self, model_size: str) -> bool:
        """判断给定的模型 ID 是否在白名单内。"""
        return any(candidate == model_size for candidate, _ in SUPPORTED_FASTER_WHISPER_MODELS)

    def is_downloaded(self, model_size: str) -> bool:
        """判断指定模型是否已经在本地缓存目录中具备必要文件（`model.bin` + `config.json`）。"""
        model_dir = self.resolve_model_dir(model_size)
        return (model_dir / "model.bin").exists() and (model_dir / "config.json").exists()

    def resolve_model_dir(self, model_size: str) -> Path:
        """返回指定模型的本地缓存目录路径（不校验是否存在）。"""
        return self._models_dir / model_size

    def resolve_model_source(self, model_size: str) -> str:
        """返回 faster-whisper 应使用的模型来源：已下载则用本地路径，否则使用远端 ID。

        faster-whisper 自身支持传入 HuggingFace 模型 ID 自动下载；为了把模型
        隔离在项目目录内，本管理器强制已下载的模型走本地路径。
        """
        model_dir = self.resolve_model_dir(model_size)
        return str(model_dir) if self.is_downloaded(model_size) else model_size

    def download(self, model_size: str, progress_reporter=None) -> Path:
        """把指定 faster-whisper 模型下载到本地缓存目录。

        流程：
            1. 校验模型 ID 在白名单内；
            2. 已存在则直接上报完成并返回本地路径；
            3. 否则从 faster-whisper `_MODELS` 拿到对应 HuggingFace 仓库 ID，
               按 `HF_ENDPOINT` 镜像（如有）下载到 `models_dir/<id>/`，
               并校验 `model.bin`/`config.json` 是否落盘。

        Args:
            model_size: 要下载的模型 ID。
            progress_reporter: 可选进度 reporter；为 `None` 时使用空实现，
                不丢失任何调用语义但不会有外部观察者。

        Returns:
            下载（已存在 / 真正下载）后的模型本地目录路径。

        Raises:
            ValueError: 模型 ID 不在白名单中。
            RuntimeError: faster-whisper 未安装或下载后缺少必要文件。
        """
        if not self.is_supported(model_size):
            raise ValueError(f"unsupported faster-whisper model '{model_size}'")

        try:
            from faster_whisper.utils import _MODELS
        except ImportError as error:
            raise RuntimeError("faster-whisper is not installed.") from error

        if self.is_downloaded(model_size):
            if progress_reporter is not None:
                progress_reporter.update("download", 100.0, "模型已存在于项目目录")
                progress_reporter.completed("模型已准备就绪")
            return self.resolve_model_dir(model_size)

        target_dir = self.resolve_model_dir(model_size)
        apply_runtime_env_overrides(self._root_dir)
        repo_id = _MODELS[model_size]
        endpoint = os.environ.get("HF_ENDPOINT", "").strip() or None
        reporter = progress_reporter or _NullProgressReporter()
        allow_patterns = (
            "config.json",
            "preprocessor_config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.*",
        )
        self._downloader.download(
            HuggingFaceDownloadSpec(
                repo_id=repo_id,
                target_dir=target_dir,
                endpoint=endpoint,
                allow_patterns=allow_patterns,
                required_files=("model.bin", "config.json"),
                required_file_patterns=(),
            ),
            reporter,
        )
        reporter.completed("模型下载完成")
        return target_dir


class _NullProgressReporter:
    """占位进度 reporter：所有调用均为 no-op，仅用于 `download` 在无 reporter 时保持接口稳定。"""

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        """空实现的进度更新，不做任何事。"""
        pass

    def completed(self, detail: str | None = None) -> None:
        """空实现的完成通知，不做任何事。"""
        pass

    def raise_if_cancelled(self) -> None:
        """空实现的取消检查，不抛异常。"""
        pass
