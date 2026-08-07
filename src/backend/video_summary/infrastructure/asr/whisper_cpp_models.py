"""whisper.cpp 的 GGML 模型规格。"""

from __future__ import annotations

from pathlib import Path

from backend.video_summary.infrastructure.asr.huggingface_asr_models import AsrModelSpec, HuggingFaceAsrModelManager
from backend.video_summary.infrastructure.asr.huggingface_model_downloader import HuggingFaceModelDownloader


SUPPORTED_WHISPER_CPP_MODELS = (
    AsrModelSpec("small", "Small", "ggerganov/whisper.cpp", ("ggml-small.bin",), ("ggml-small.bin",)),
    AsrModelSpec("medium", "Medium", "ggerganov/whisper.cpp", ("ggml-medium.bin",), ("ggml-medium.bin",)),
    AsrModelSpec("large-v3", "Large V3", "ggerganov/whisper.cpp", ("ggml-large-v3.bin",), ("ggml-large-v3.bin",)),
    AsrModelSpec("large-v3-turbo-q5_0", "Large V3 Turbo Q5_0", "ggerganov/whisper.cpp", ("ggml-large-v3-turbo-q5_0.bin",), ("ggml-large-v3-turbo-q5_0.bin",), recommended=True),
)


class WhisperCppModelManager(HuggingFaceAsrModelManager):
    """管理供外部 ``whisper-cli`` 使用的 GGML 模型。"""

    def __init__(self, models_dir: Path, *, downloader: HuggingFaceModelDownloader | None = None) -> None:
        super().__init__(models_dir, specs=SUPPORTED_WHISPER_CPP_MODELS, downloader=downloader)
