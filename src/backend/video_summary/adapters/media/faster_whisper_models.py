from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from backend.video_summary.adapters.media.huggingface_model_downloader import (
    HuggingFaceDownloadSpec,
    HuggingFaceModelDownloader,
)
from backend.video_summary.configuration.settings import apply_runtime_env_overrides


SUPPORTED_FASTER_WHISPER_MODELS = (
    ("small", "Small"),
    ("medium", "Medium"),
    ("large-v3", "Large V3"),
    ("large-v3-turbo", "Large V3 Turbo"),
)


@dataclass(frozen=True)
class FasterWhisperModelInfo:
    id: str
    label: str
    downloaded: bool
    current: bool
    recommended: bool


class FasterWhisperModelManager:
    def __init__(
        self,
        models_dir: Path,
        *,
        downloader: HuggingFaceModelDownloader | None = None,
    ) -> None:
        self._models_dir = models_dir
        self._root_dir = models_dir.parents[2]
        self._downloader = downloader or HuggingFaceModelDownloader()

    def list_models(self, current_model_size: str) -> list[FasterWhisperModelInfo]:
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
        return any(candidate == model_size for candidate, _ in SUPPORTED_FASTER_WHISPER_MODELS)

    def is_downloaded(self, model_size: str) -> bool:
        model_dir = self.resolve_model_dir(model_size)
        return (model_dir / "model.bin").exists() and (model_dir / "config.json").exists()

    def resolve_model_dir(self, model_size: str) -> Path:
        return self._models_dir / model_size

    def resolve_model_source(self, model_size: str) -> str:
        model_dir = self.resolve_model_dir(model_size)
        return str(model_dir) if self.is_downloaded(model_size) else model_size

    def download(self, model_size: str, progress_reporter=None) -> Path:
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
    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        pass

    def completed(self, detail: str | None = None) -> None:
        pass

    def raise_if_cancelled(self) -> None:
        pass
