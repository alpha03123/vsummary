"""faster-whisper 的模型规格与通用 ASR 模型管理器适配。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backend.video_summary.infrastructure.asr.huggingface_asr_models import (
    AsrModelInfo as FasterWhisperModelInfo,
    AsrModelSpec,
    HuggingFaceAsrModelManager,
)
from backend.video_summary.infrastructure.asr.huggingface_model_downloader import HuggingFaceModelDownloader


_FASTER_WHISPER_FILES = (
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
)

SUPPORTED_FASTER_WHISPER_MODELS = (
    AsrModelSpec("small", "Small", None, ("model.bin", "config.json"), _FASTER_WHISPER_FILES),
    AsrModelSpec("medium", "Medium", None, ("model.bin", "config.json"), _FASTER_WHISPER_FILES),
    AsrModelSpec("large-v3", "Large V3", None, ("model.bin", "config.json"), _FASTER_WHISPER_FILES),
    AsrModelSpec("large-v3-turbo", "Large V3 Turbo", None, ("model.bin", "config.json"), _FASTER_WHISPER_FILES, recommended=True),
)


class FasterWhisperModelManager(HuggingFaceAsrModelManager):
    """管理 CTranslate2 格式的 faster-whisper 模型。"""

    def __init__(self, models_dir: Path, *, downloader: HuggingFaceModelDownloader | None = None) -> None:
        super().__init__(models_dir, specs=SUPPORTED_FASTER_WHISPER_MODELS, downloader=downloader)

    def resolve_model_source(self, model_size: str) -> str:
        """优先返回项目目录中的模型；未下载时保留远端模型 ID。"""
        return str(self.resolve_model_dir(model_size)) if self.is_downloaded(model_size) else model_size

    def download_spec(self, model_id: str) -> AsrModelSpec:
        """以当前 faster-whisper 安装包的官方仓库映射作为下载来源。"""
        try:
            from faster_whisper.utils import _MODELS
        except ImportError as error:
            raise RuntimeError("faster-whisper is not installed.") from error
        return replace(super().download_spec(model_id), repo_id=_MODELS[model_id])
