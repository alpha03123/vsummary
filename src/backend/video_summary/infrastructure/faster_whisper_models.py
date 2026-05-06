from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
import os
from pathlib import Path
import shutil

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


@dataclass(frozen=True)
class _RepoFile:
    path: str
    size: int | None


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
            from huggingface_hub import HfApi
        except ImportError as error:
            raise RuntimeError("faster-whisper is not installed.") from error

        if self.is_downloaded(model_size):
            if progress_reporter is not None:
                progress_reporter.update("download", 100.0, "模型已存在于项目目录")
                progress_reporter.completed("模型已准备就绪")
            return self.resolve_model_dir(model_size)

        target_dir = self.resolve_model_dir(model_size)
        temp_dir = target_dir.with_name(f".{target_dir.name}.download")
        apply_runtime_env_overrides(self._root_dir)
        repo_id = _MODELS[model_size]
        endpoint = os.environ.get("HF_ENDPOINT", "").strip() or None
        allow_patterns = (
            "config.json",
            "preprocessor_config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.*",
        )
        api = HfApi(endpoint=endpoint) if endpoint else HfApi()
        if progress_reporter is not None:
            progress_reporter.update("download", 0.0, f"正在连接模型仓库：{repo_id}")
        files = _list_repo_files(api=api, repo_id=repo_id, allow_patterns=allow_patterns)
        files = _with_resolved_file_sizes(repo_id=repo_id, files=files, endpoint=endpoint)
        total_bytes = _sum_known_file_sizes(files)
        if progress_reporter is not None:
            progress_reporter.raise_if_cancelled()
        try:
            _remove_path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            _download_repo_files(
                repo_id=repo_id,
                files=files,
                target_dir=temp_dir,
                endpoint=endpoint,
                progress_reporter=progress_reporter,
                total_bytes=total_bytes,
            )
            if progress_reporter is not None:
                progress_reporter.raise_if_cancelled()
                progress_reporter.update("download", 99.0, "正在校验模型文件")
            if not (temp_dir / "model.bin").is_file() or not (temp_dir / "config.json").is_file():
                raise RuntimeError("模型下载完成但缺少必要文件。")
            _remove_path(target_dir)
            temp_dir.replace(target_dir)
            if progress_reporter is not None:
                progress_reporter.completed("模型下载完成")
        except Exception:
            _remove_path(temp_dir)
            raise
        return target_dir


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _list_repo_files(*, api, repo_id: str, allow_patterns: tuple[str, ...]) -> list[_RepoFile]:
    try:
        info = api.model_info(repo_id, files_metadata=True)
    except Exception as error:
        raise RuntimeError(f"无法读取模型仓库信息：{repo_id}") from error
    files: list[_RepoFile] = []
    for sibling in info.siblings:
        path = str(getattr(sibling, "rfilename", "")).strip()
        if not path or not _matches_any_pattern(path, allow_patterns):
            continue
        size = getattr(sibling, "size", None)
        files.append(_RepoFile(path=path, size=size if isinstance(size, int) else None))
    if not files:
        raise RuntimeError(f"模型仓库没有匹配的 faster-whisper 文件：{repo_id}")
    return sorted(files, key=lambda item: item.path)


def _matches_any_pattern(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def _sum_known_file_sizes(files: list[_RepoFile]) -> int | None:
    total = sum(file.size for file in files if isinstance(file.size, int))
    return total if total > 0 else None


def _with_resolved_file_sizes(
    *,
    repo_id: str,
    files: list[_RepoFile],
    endpoint: str | None,
) -> list[_RepoFile]:
    if all(isinstance(file.size, int) for file in files):
        return files

    from huggingface_hub import hf_hub_url
    import requests

    resolved: list[_RepoFile] = []
    for file in files:
        if isinstance(file.size, int):
            resolved.append(file)
            continue
        size = None
        try:
            response = requests.head(
                hf_hub_url(repo_id, file.path, endpoint=endpoint),
                allow_redirects=True,
                timeout=(10, 30),
            )
            if response.ok:
                size = _resolve_response_total_bytes(response)
        except requests.RequestException:
            size = None
        resolved.append(_RepoFile(path=file.path, size=size))
    return resolved


def _download_repo_files(
    *,
    repo_id: str,
    files: list[_RepoFile],
    target_dir: Path,
    endpoint: str | None,
    progress_reporter,
    total_bytes: int | None,
) -> None:
    from huggingface_hub import hf_hub_url
    import requests

    downloaded_bytes = 0
    for file in files:
        if progress_reporter is not None:
            progress_reporter.raise_if_cancelled()
        destination = target_dir / file.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        url = hf_hub_url(repo_id, file.path, endpoint=endpoint)
        detail = f"正在下载 {file.path}"
        _report_download_progress(
            progress_reporter=progress_reporter,
            downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes,
            detail=detail,
        )
        with requests.get(url, stream=True, timeout=(10, 30)) as response:
            response.raise_for_status()
            fallback_total = _resolve_response_total_bytes(response)
            with destination.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if progress_reporter is not None:
                        progress_reporter.raise_if_cancelled()
                    if not chunk:
                        continue
                    output.write(chunk)
                    downloaded_bytes += len(chunk)
                    _report_download_progress(
                        progress_reporter=progress_reporter,
                        downloaded_bytes=downloaded_bytes,
                        total_bytes=total_bytes or fallback_total,
                        detail=detail,
                    )
        if file.size is not None and destination.stat().st_size != file.size:
            raise RuntimeError(f"模型文件大小校验失败：{file.path}")


def _resolve_response_total_bytes(response) -> int | None:
    value = response.headers.get("Content-Length")
    if not value:
        return None
    try:
        total = int(value)
    except ValueError:
        return None
    return total if total > 0 else None


def _report_download_progress(
    *,
    progress_reporter,
    downloaded_bytes: int,
    total_bytes: int | None,
    detail: str,
) -> None:
    if progress_reporter is None:
        return
    progress = None
    if total_bytes and total_bytes > 0:
        progress = min(98.0, (downloaded_bytes / total_bytes) * 98.0)
    progress_reporter.update("download", progress, detail)
