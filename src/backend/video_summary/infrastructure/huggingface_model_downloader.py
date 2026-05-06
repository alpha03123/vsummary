from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
import shutil
from typing import Callable

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
        model_info_loader: Callable[[str, str | None], object] | None = None,
        http_get: Callable[..., object] | None = None,
    ) -> None:
        self._model_info_loader = model_info_loader
        self._http_get = http_get

    def download(self, spec: HuggingFaceDownloadSpec, reporter: ProgressReporter) -> Path:
        temp_dir = spec.target_dir.with_name(f".{spec.target_dir.name}.download")
        reporter.update("download", 0.0, f"正在连接模型仓库：{spec.repo_id}")
        files = self._list_repo_files(spec)
        total_bytes = _sum_known_file_sizes(files)
        reporter.raise_if_cancelled()

        try:
            _remove_path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            self._download_files(
                spec=spec,
                files=files,
                target_dir=temp_dir,
                total_bytes=total_bytes,
                reporter=reporter,
            )
            reporter.raise_if_cancelled()
            reporter.update("validate", 95.0, f"正在校验模型文件：{spec.repo_id}")
            _validate_downloaded_model(temp_dir, spec)
            _remove_path(spec.target_dir)
            temp_dir.replace(spec.target_dir)
        except Exception:
            _remove_path(temp_dir)
            raise
        return spec.target_dir

    def _list_repo_files(self, spec: HuggingFaceDownloadSpec) -> list["_RepoFile"]:
        info = self._load_model_info(spec.repo_id, spec.endpoint)
        files: list[_RepoFile] = []
        for sibling in getattr(info, "siblings", ()):
            path = str(getattr(sibling, "rfilename", "")).strip()
            if not path or (spec.allow_patterns and not _matches_any_pattern(path, spec.allow_patterns)):
                continue
            size = getattr(sibling, "size", None)
            files.append(_RepoFile(path=path, size=size if isinstance(size, int) else None))
        if not files:
            raise RuntimeError(f"模型仓库没有匹配的文件：{spec.repo_id}")
        return sorted(files, key=lambda item: item.path)

    def _load_model_info(self, repo_id: str, endpoint: str | None) -> object:
        if self._model_info_loader is not None:
            return self._model_info_loader(repo_id, endpoint)

        from huggingface_hub import HfApi

        api = HfApi(endpoint=endpoint) if endpoint else HfApi()
        return api.model_info(repo_id, files_metadata=True)

    def _download_files(
        self,
        *,
        spec: HuggingFaceDownloadSpec,
        files: list["_RepoFile"],
        target_dir: Path,
        total_bytes: int | None,
        reporter: ProgressReporter,
    ) -> None:
        from huggingface_hub import hf_hub_url

        downloaded_bytes = 0
        for file in files:
            reporter.raise_if_cancelled()
            destination = target_dir / file.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            detail = f"正在下载 {file.path}"
            reporter.update(
                "download",
                _resolve_download_progress(downloaded_bytes=downloaded_bytes, total_bytes=total_bytes),
                detail,
            )
            url = hf_hub_url(spec.repo_id, file.path, endpoint=spec.endpoint)
            downloaded_bytes = self._download_file(
                url=url,
                destination=destination,
                detail=detail,
                downloaded_bytes=downloaded_bytes,
                total_bytes=total_bytes or file.size,
                reporter=reporter,
            )
            if file.size is not None and destination.stat().st_size != file.size:
                raise RuntimeError(f"模型文件大小校验失败：{file.path}")

    def _download_file(
        self,
        *,
        url: str,
        destination: Path,
        detail: str,
        downloaded_bytes: int,
        total_bytes: int | None,
        reporter: ProgressReporter,
    ) -> int:
        http_get = self._http_get
        if http_get is None:
            import requests

            http_get = requests.get

        with http_get(url, stream=True, timeout=(10, 30)) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    reporter.raise_if_cancelled()
                    if not chunk:
                        continue
                    output.write(chunk)
                    downloaded_bytes += len(chunk)
                    reporter.raise_if_cancelled()
                    reporter.update(
                        "download",
                        _resolve_download_progress(downloaded_bytes=downloaded_bytes, total_bytes=total_bytes),
                        detail,
                    )
        return downloaded_bytes


@dataclass(frozen=True)
class _RepoFile:
    path: str
    size: int | None


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


def _matches_any_pattern(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def _sum_known_file_sizes(files: list[_RepoFile]) -> int | None:
    total = sum(file.size for file in files if isinstance(file.size, int))
    return total if total > 0 else None


def _resolve_download_progress(*, downloaded_bytes: int, total_bytes: int | None) -> float | None:
    if total_bytes is None or total_bytes <= 0:
        return None
    return min(94.0, max(1.0, (downloaded_bytes / total_bytes) * 94.0))
