from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
import shutil

from backend.video_summary.summary_generation.ports import ProgressReporter


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
    def download(self, spec: HuggingFaceDownloadSpec, reporter: ProgressReporter) -> Path:
        temp_dir = spec.target_dir.with_name(f".{spec.target_dir.name}.download")
        reporter.update("download", 0.0, f"正在连接模型仓库：{spec.repo_id}")
        reporter.raise_if_cancelled()

        try:
            _remove_path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            reporter.update("download", 5.0, f"正在下载模型文件：{spec.repo_id}")
            self._snapshot_download(spec=spec, temp_dir=temp_dir)
            reporter.raise_if_cancelled()
            reporter.update("validate", 95.0, f"正在校验模型文件：{spec.repo_id}")
            _validate_downloaded_model(temp_dir, spec)
            _remove_path(spec.target_dir)
            temp_dir.replace(spec.target_dir)
        except Exception:
            _remove_path(temp_dir)
            raise
        return spec.target_dir

    def _snapshot_download(self, *, spec: HuggingFaceDownloadSpec, temp_dir: Path) -> None:
        from huggingface_hub import snapshot_download

        kwargs: dict[str, object] = {
            "repo_id": spec.repo_id,
            "local_dir": temp_dir,
            "max_workers": spec.max_workers,
        }
        if spec.endpoint:
            kwargs["endpoint"] = spec.endpoint
        if spec.allow_patterns:
            kwargs["allow_patterns"] = spec.allow_patterns
        snapshot_download(**kwargs)


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
