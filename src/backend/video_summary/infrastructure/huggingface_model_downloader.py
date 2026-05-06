from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
import shutil
from typing import Any, Callable

from backend.video_summary.generation.ports import ProgressReporter


@dataclass(frozen=True)
class HuggingFaceDownloadSpec:
    repo_id: str
    target_dir: Path
    required_files: tuple[str, ...]
    required_file_patterns: tuple[str, ...]
    allow_patterns: tuple[str, ...] = ()
    endpoint: str | None = None
    max_workers: int = 4


class HuggingFaceModelDownloader:
    def __init__(
        self,
        *,
        snapshot_download: Callable[..., object] | None = None,
        model_info_loader: Callable[[str, str | None], object] | None = None,
    ) -> None:
        self._snapshot_download = snapshot_download
        self._model_info_loader = model_info_loader

    def download(self, spec: HuggingFaceDownloadSpec, reporter: ProgressReporter) -> Path:
        temp_dir = spec.target_dir.with_name(f".{spec.target_dir.name}.download")
        reporter.update("download", 0.0, f"正在连接模型仓库：{spec.repo_id}")
        total_bytes = self._get_expected_download_size(spec.repo_id, endpoint=spec.endpoint)
        tqdm_class = build_download_tqdm_class(
            progress_reporter=reporter,
            total_bytes=total_bytes,
            repo_id=spec.repo_id,
        )
        reporter.raise_if_cancelled()

        try:
            _remove_path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            self._call_snapshot_download(spec=spec, temp_dir=temp_dir, tqdm_class=tqdm_class)
            reporter.raise_if_cancelled()
            reporter.update("validate", 95.0, f"正在校验模型文件：{spec.repo_id}")
            _validate_downloaded_model(temp_dir, spec)
            _remove_path(spec.target_dir)
            temp_dir.replace(spec.target_dir)
        except Exception:
            _remove_path(temp_dir)
            raise
        return spec.target_dir

    def _call_snapshot_download(self, *, spec: HuggingFaceDownloadSpec, temp_dir: Path, tqdm_class) -> None:
        snapshot_download = self._snapshot_download
        if snapshot_download is None:
            from huggingface_hub import snapshot_download as hf_snapshot_download

            snapshot_download = hf_snapshot_download

        kwargs: dict[str, object] = {
            "repo_id": spec.repo_id,
            "local_dir": temp_dir,
            "max_workers": spec.max_workers,
            "tqdm_class": tqdm_class,
        }
        if spec.endpoint:
            kwargs["endpoint"] = spec.endpoint
        if spec.allow_patterns:
            kwargs["allow_patterns"] = spec.allow_patterns
        snapshot_download(**kwargs)

    def _get_expected_download_size(self, repo_id: str, *, endpoint: str | None) -> int | None:
        try:
            info = self._load_model_info(repo_id, endpoint)
        except Exception:
            return None

        total = 0
        has_size = False
        for sibling in getattr(info, "siblings", ()):
            size = getattr(sibling, "size", None)
            if isinstance(size, int):
                total += size
                has_size = True
        return total if has_size else None

    def _load_model_info(self, repo_id: str, endpoint: str | None) -> object:
        if self._model_info_loader is not None:
            return self._model_info_loader(repo_id, endpoint)

        from huggingface_hub import HfApi

        api = HfApi(endpoint=endpoint) if endpoint else HfApi()
        return api.model_info(repo_id, files_metadata=True)


class _DownloadProgressCoordinator:
    def __init__(self, progress_reporter: ProgressReporter, total_bytes: int | None, repo_id: str) -> None:
        self._progress_reporter = progress_reporter
        self._total_bytes = total_bytes
        self._repo_id = repo_id
        self._bars: dict[int, int] = {}
        self._bar_totals: dict[int, int] = {}

    def update(self, bar: Any) -> None:
        self._progress_reporter.raise_if_cancelled()
        key = id(bar)
        current_n = int(getattr(bar, "n", 0) or 0)
        total = int(getattr(bar, "total", 0) or 0)
        if total > 0:
            self._bars[key] = min(current_n, total)
            self._bar_totals[key] = total

        progress = self._resolve_progress(current_n=current_n, total=total)
        filename = _extract_filename(getattr(bar, "desc", None))
        detail = f"正在下载 {filename}" if filename else f"正在下载模型：{self._repo_id}"
        self._progress_reporter.update("download", progress, detail)

    def finalize_bar(self, bar: Any) -> None:
        key = id(bar)
        total = int(getattr(bar, "total", 0) or 0)
        if total > 0:
            self._bars[key] = total
            self._bar_totals[key] = total

    def _resolve_progress(self, *, current_n: int, total: int) -> float | None:
        if self._total_bytes and self._total_bytes > 0 and self._bars:
            return min(94.0, max(1.0, (sum(self._bars.values()) / self._total_bytes) * 94.0))
        if total > 0:
            return min(94.0, max(1.0, (current_n / total) * 94.0))
        if self._bar_totals:
            known_total = sum(self._bar_totals.values())
            if known_total > 0:
                return min(94.0, max(1.0, (sum(self._bars.values()) / known_total) * 94.0))
        return None


def build_download_tqdm_class(
    *,
    progress_reporter: ProgressReporter,
    total_bytes: int | None,
    repo_id: str,
):
    from tqdm.auto import tqdm

    coordinator = _DownloadProgressCoordinator(progress_reporter, total_bytes, repo_id)

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


def _validate_downloaded_model(model_dir: Path, spec: HuggingFaceDownloadSpec) -> None:
    missing_files = [file_name for file_name in spec.required_files if not (model_dir / file_name).is_file()]
    if missing_files:
        raise RuntimeError(f"模型下载完成但缺少必要文件：{', '.join(missing_files)}")
    if spec.required_file_patterns and not any(
        fnmatch(path.name, pattern)
        for path in model_dir.rglob("*")
        if path.is_file()
        for pattern in spec.required_file_patterns
    ):
        patterns = ", ".join(spec.required_file_patterns)
        raise RuntimeError(f"模型下载完成但缺少匹配文件：{patterns}")


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _extract_filename(desc: object) -> str | None:
    if not isinstance(desc, str):
        return None
    value = desc.strip()
    if not value:
        return None
    return value.split(":", 1)[0].strip()
