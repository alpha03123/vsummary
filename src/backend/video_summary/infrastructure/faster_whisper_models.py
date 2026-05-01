from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.video_summary.infrastructure.settings import apply_runtime_env_overrides


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
        self._root_dir = models_dir.parents[2]

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
            from huggingface_hub import HfApi, snapshot_download
        except ImportError as error:
            raise RuntimeError("faster-whisper is not installed.") from error

        if self.is_downloaded(model_size):
            if progress_reporter is not None:
                progress_reporter.update("download", 100.0, "模型已存在于项目目录")
                progress_reporter.completed("模型已准备就绪")
            return self.resolve_model_dir(model_size)

        target_dir = self.resolve_model_dir(model_size)
        target_dir.mkdir(parents=True, exist_ok=True)
        apply_runtime_env_overrides(self._root_dir)
        repo_id = _MODELS[model_size]
        total_bytes = _get_expected_download_size(repo_id)
        tqdm_class = _build_download_tqdm_class(
            progress_reporter=progress_reporter,
            total_bytes=total_bytes,
        )
        snapshot_download(
            repo_id,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
            allow_patterns=[
                "config.json",
                "preprocessor_config.json",
                "model.bin",
                "tokenizer.json",
                "vocabulary.*",
            ],
            tqdm_class=tqdm_class,
            max_workers=1,
        )
        if progress_reporter is not None:
            progress_reporter.completed("模型下载完成")
        return target_dir


def _get_expected_download_size(repo_id: str) -> int | None:
    from huggingface_hub import HfApi

    info = HfApi().model_info(repo_id, files_metadata=True)
    total = 0
    has_size = False
    for sibling in info.siblings:
        if sibling.rfilename in {"config.json", "preprocessor_config.json", "model.bin", "tokenizer.json"} or sibling.rfilename.startswith("vocabulary."):
            size = getattr(sibling, "size", None)
            if isinstance(size, int):
                total += size
                has_size = True
    return total if has_size else None


class _DownloadProgressCoordinator:
    def __init__(self, progress_reporter, total_bytes: int | None) -> None:
        self._progress_reporter = progress_reporter
        self._total_bytes = total_bytes
        self._completed_bytes = 0
        self._current_key: int | None = None
        self._current_total = 0

    def update(self, bar: Any) -> None:
        if self._progress_reporter is None:
            return
        self._progress_reporter.raise_if_cancelled()
        key = id(bar)
        if self._current_key != key:
            self._current_key = key
            self._current_total = int(bar.total or 0)
        filename = _extract_filename(getattr(bar, "desc", None))
        current_n = int(getattr(bar, "n", 0) or 0)
        if self._total_bytes and self._total_bytes > 0:
            progress = ((self._completed_bytes + current_n) / self._total_bytes) * 100.0
        elif self._current_total > 0:
            progress = (current_n / self._current_total) * 100.0
        else:
            progress = None
        detail = f"正在下载 {filename}" if filename else "正在下载模型文件"
        self._progress_reporter.update("download", progress, detail)

    def finalize_bar(self, bar: Any) -> None:
        if self._current_key != id(bar):
            return
        self._completed_bytes += self._current_total
        self._current_key = None
        self._current_total = 0


def _build_download_tqdm_class(progress_reporter, total_bytes: int | None):
    try:
        from tqdm.auto import tqdm
    except ImportError as error:
        raise RuntimeError("tqdm is required to report download progress.") from error

    coordinator = _DownloadProgressCoordinator(progress_reporter, total_bytes)

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
    parts = desc.strip().split(":")
    return parts[0].strip() if parts else None
