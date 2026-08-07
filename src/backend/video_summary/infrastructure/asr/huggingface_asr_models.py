"""本地 HuggingFace ASR 模型的通用目录、状态与下载管理。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from backend.video_summary.infrastructure.asr.huggingface_model_downloader import (
    HuggingFaceDownloadSpec,
    HuggingFaceModelDownloader,
)
from backend.video_summary.infrastructure.config.settings import apply_runtime_env_overrides


@dataclass(frozen=True)
class AsrModelSpec:
    """一个 ASR provider 可下载模型的不可变规格。"""

    id: str
    label: str
    repo_id: str | None
    required_files: tuple[str, ...]
    allow_patterns: tuple[str, ...]
    recommended: bool = False


@dataclass(frozen=True)
class AsrModelInfo:
    """单个 ASR 模型在 API 与设置页展示用的状态快照。"""

    id: str
    label: str
    downloaded: bool
    current: bool
    recommended: bool


class HuggingFaceAsrModelManager:
    """复用下载器管理某个本地 ASR provider 的模型目录。"""

    def __init__(
        self,
        models_dir: Path,
        *,
        specs: tuple[AsrModelSpec, ...],
        downloader: HuggingFaceModelDownloader | None = None,
    ) -> None:
        self._models_dir = models_dir
        self._specs = {spec.id: spec for spec in specs}
        self._root_dir = models_dir.parents[2]
        self._downloader = downloader or HuggingFaceModelDownloader()

    def list_models(self, current_model: str) -> list[AsrModelInfo]:
        return [
            AsrModelInfo(
                id=spec.id,
                label=spec.label,
                downloaded=self.is_downloaded(spec.id),
                current=spec.id == current_model,
                recommended=spec.recommended,
            )
            for spec in self._specs.values()
        ]

    def is_supported(self, model_id: str) -> bool:
        return model_id in self._specs

    def is_downloaded(self, model_id: str) -> bool:
        spec = self._get_spec(model_id)
        model_dir = self.resolve_model_dir(model_id)
        return all((model_dir / required_file).is_file() for required_file in spec.required_files)

    def resolve_model_dir(self, model_id: str) -> Path:
        self._get_spec(model_id)
        return self._models_dir / model_id

    def resolve_model_path(self, model_id: str) -> Path:
        spec = self._get_spec(model_id)
        return self.resolve_model_dir(model_id) / spec.required_files[0]

    def download(self, model_id: str, progress_reporter=None) -> Path:
        spec = self.download_spec(model_id)
        if not spec.repo_id:
            raise RuntimeError(f"ASR 模型 '{model_id}' 未提供 Hugging Face 仓库。")
        reporter = progress_reporter or _NullProgressReporter()
        target_dir = self.resolve_model_dir(model_id)
        if self.is_downloaded(model_id):
            reporter.update("download", 100.0, "模型已存在于项目目录")
            reporter.completed("模型已准备就绪")
            return target_dir

        apply_runtime_env_overrides(self._root_dir)
        self._downloader.download(
            HuggingFaceDownloadSpec(
                repo_id=spec.repo_id,
                target_dir=target_dir,
                endpoint=os.environ.get("HF_ENDPOINT", "").strip() or None,
                allow_patterns=spec.allow_patterns,
                required_files=spec.required_files,
                required_file_patterns=(),
            ),
            reporter,
        )
        reporter.completed("模型下载完成")
        return target_dir

    def _get_spec(self, model_id: str) -> AsrModelSpec:
        try:
            return self._specs[model_id]
        except KeyError as error:
            raise ValueError(f"unsupported ASR model '{model_id}'") from error

    def download_spec(self, model_id: str) -> AsrModelSpec:
        """返回下载时使用的模型规格；provider 可覆写以解析运行时仓库映射。"""
        return self._get_spec(model_id)


class _NullProgressReporter:
    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        del stage, progress, detail

    def completed(self, detail: str | None = None) -> None:
        del detail

    def is_cancel_requested(self) -> bool:
        return False

    def raise_if_cancelled(self) -> None:
        return None
