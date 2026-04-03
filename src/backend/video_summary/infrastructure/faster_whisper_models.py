from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    def __init__(self, models_dir: Path) -> None:
        self._models_dir = models_dir

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

    def download(self, model_size: str) -> Path:
        if not self.is_supported(model_size):
            raise ValueError(f"unsupported faster-whisper model '{model_size}'")

        try:
            from faster_whisper.utils import download_model
        except ImportError as error:
            raise RuntimeError("faster-whisper is not installed.") from error

        target_dir = self.resolve_model_dir(model_size)
        target_dir.mkdir(parents=True, exist_ok=True)
        download_model(model_size, output_dir=str(target_dir))
        return target_dir
