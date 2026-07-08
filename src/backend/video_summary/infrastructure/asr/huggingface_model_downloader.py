"""HuggingFace 模型下载的统一封装（含进度、校验、原子替换）。

业务场景：fastembed/faster-whisper 都需要在用户机器上预下载大模型；本类提供
一份"下载 → 校验 → 原子替换"的统一流程：
1. 先把文件下载到 `.{target}.download/` 临时目录；
2. 校验必要文件/通配文件存在；
3. 校验通过后用 `Path.replace` 把临时目录替换为正式目录（原子）；
4. 任何环节失败都会清理临时目录，避免污染目标位置。
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
import shutil
from typing import Any

from backend.video_summary.generation.ports import ProgressReporter


@dataclass(frozen=True)
class HuggingFaceDownloadSpec:
    """单次下载任务所需的全部参数。

    Attributes:
        repo_id: HuggingFace 仓库 ID（`owner/name` 形式）。
        target_dir: 下载完成后落地的目标目录。
        required_files: 必须存在的具体文件名列表（缺失则报错）。
        required_file_patterns: 必须至少匹配一个的通配符列表（如 `tokenizer.*`）。
        allow_patterns: 传给 `snapshot_download` 的 `allow_patterns`，用于限制下载范围。
        endpoint: 自定义 HuggingFace 镜像（对应 `HF_ENDPOINT` 环境变量）。
        max_workers: 并发下载线程数，默认 4。
    """

    repo_id: str
    target_dir: Path
    required_files: tuple[str, ...]
    required_file_patterns: tuple[str, ...]
    allow_patterns: tuple[str, ...] = ()
    endpoint: str | None = None
    max_workers: int = 4


class HuggingFaceDownloadCancelled(RuntimeError):
    """HuggingFace 模型下载被用户取消。"""


class HuggingFaceModelDownloader:
    """统一的 HuggingFace 模型下载器。

    进度上报通过传入的 `ProgressReporter` 完成：
    - `0%`：刚发起；
    - `5%`：开始下载文件；
    - `95%`：进入校验阶段；
    - `100%` / `completed()`：校验通过、原子替换完成。
    """

    def download(self, spec: HuggingFaceDownloadSpec, reporter: ProgressReporter) -> Path:
        """执行一次完整的下载 → 校验 → 原子替换流程。

        Args:
            spec: 下载任务参数。
            reporter: 用于上报进度与响应取消的 reporter；调用方应保证其线程安全。

        Returns:
            最终目标目录路径（即 `spec.target_dir`）。

        Raises:
            Exception: 任何步骤失败都会先清理临时目录，再原样上抛；常见的
                `RuntimeError` 来源于"校验时缺少必要文件"。
        """
        temp_dir = spec.target_dir.with_name(f".{spec.target_dir.name}.download")
        reporter.update("download", 0.0, f"正在连接模型仓库：{spec.repo_id}")
        _raise_if_download_cancelled(reporter)

        try:
            _remove_path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            reporter.update("download", 5.0, f"正在下载模型文件：{spec.repo_id}")
            self._snapshot_download(spec=spec, temp_dir=temp_dir, reporter=reporter)
            _raise_if_download_cancelled(reporter)
            reporter.update("validate", 95.0, f"正在校验模型文件：{spec.repo_id}")
            _validate_downloaded_model(temp_dir, spec)
            _remove_path(spec.target_dir)
            temp_dir.replace(spec.target_dir)
        except Exception:
            _remove_path(temp_dir)
            raise
        return spec.target_dir

    def _snapshot_download(self, *, spec: HuggingFaceDownloadSpec, temp_dir: Path, reporter: ProgressReporter) -> None:
        """按 HuggingFace 仓库文件清单下载到本地目录，并在真实文件流中响应取消。"""
        from huggingface_hub import HfApi, hf_hub_url
        from huggingface_hub import constants
        from huggingface_hub.utils import build_hf_headers, get_session, hf_raise_for_status

        api = HfApi(endpoint=spec.endpoint)
        model_info = api.model_info(spec.repo_id, files_metadata=True)
        files = _select_repo_files(model_info.siblings, spec.allow_patterns)
        if not files:
            raise RuntimeError(f"模型仓库未匹配到需要下载的文件：{spec.repo_id}")

        total_bytes = _sum_known_sizes(files)
        downloaded_bytes = 0
        headers = build_hf_headers()
        session = get_session()
        for file_info in files:
            _raise_if_download_cancelled(reporter)
            filename = str(file_info.rfilename)
            target_path = temp_dir / filename
            target_path.parent.mkdir(parents=True, exist_ok=True)
            url = hf_hub_url(spec.repo_id, filename, endpoint=spec.endpoint)
            with session.get(
                url,
                headers=headers,
                stream=True,
                timeout=constants.HF_HUB_DOWNLOAD_TIMEOUT,
            ) as response:
                hf_raise_for_status(response)
                with target_path.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=constants.DOWNLOAD_CHUNK_SIZE):
                        _raise_if_download_cancelled(reporter)
                        if not chunk:
                            continue
                        output.write(chunk)
                        downloaded_bytes += len(chunk)
                        reporter.update(
                            "download",
                            _calculate_download_progress(downloaded_bytes, total_bytes),
                            f"正在下载模型文件：{filename}",
                        )
                        _raise_if_download_cancelled(reporter)
            expected_size = _file_size(file_info)
            if expected_size is not None and target_path.stat().st_size != expected_size:
                raise RuntimeError(
                    f"模型文件下载不完整：{filename}，期望 {expected_size} bytes，实际 {target_path.stat().st_size} bytes"
                )


def _raise_if_download_cancelled(reporter: ProgressReporter) -> None:
    """把通用 reporter 取消信号转换为下载器专用异常。"""
    if reporter.is_cancel_requested():
        raise HuggingFaceDownloadCancelled("模型下载已取消")
    try:
        reporter.raise_if_cancelled()
    except RuntimeError as error:
        if "取消" in str(error):
            raise HuggingFaceDownloadCancelled("模型下载已取消") from error
        raise


def _select_repo_files(siblings: list[Any], allow_patterns: tuple[str, ...]) -> list[Any]:
    """按 `allow_patterns` 选择需要下载的仓库文件。"""
    return [
        file_info
        for file_info in siblings
        if _is_allowed_repo_file(str(getattr(file_info, "rfilename", "")), allow_patterns)
    ]


def _is_allowed_repo_file(filename: str, allow_patterns: tuple[str, ...]) -> bool:
    """判断仓库文件名是否匹配下载规则。"""
    if not filename or filename.endswith("/"):
        return False
    if not allow_patterns:
        return True
    basename = Path(filename).name
    return any(fnmatch(filename, pattern) or fnmatch(basename, pattern) for pattern in allow_patterns)


def _sum_known_sizes(files: list[Any]) -> int | None:
    """汇总已知文件大小；任一文件缺少 size 时返回 None。"""
    sizes = [_file_size(file_info) for file_info in files]
    if any(size is None for size in sizes):
        return None
    return sum(size for size in sizes if size is not None)


def _file_size(file_info: Any) -> int | None:
    """读取 HuggingFace sibling 的文件大小，兼容不同版本字段。"""
    size = getattr(file_info, "size", None)
    if isinstance(size, int):
        return size
    lfs = getattr(file_info, "lfs", None)
    if isinstance(lfs, dict) and isinstance(lfs.get("size"), int):
        return lfs["size"]
    return None


def _calculate_download_progress(downloaded_bytes: int, total_bytes: int | None) -> float | None:
    """把字节下载进度映射到 5%-95% 的下载阶段区间。"""
    if total_bytes is None or total_bytes <= 0:
        return None
    return 5.0 + min(90.0, (downloaded_bytes / total_bytes) * 90.0)


def _validate_downloaded_model(model_dir: Path, spec: HuggingFaceDownloadSpec) -> None:
    """校验下载后的模型是否齐全。

    两层校验：
        1. `spec.required_files` 中列出的每个具体文件都必须存在；
        2. `spec.required_file_patterns` 中至少要有一个通配符命中 `model_dir` 下的某文件。

    Args:
        model_dir: 已下载的临时模型目录。
        spec: 携带校验规则的下载任务参数。

    Raises:
        RuntimeError: 任一校验失败时抛出，错误信息会列出缺失的具体/通配项。
    """
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
    """删除文件或目录：目录用 `shutil.rmtree`，文件用 `unlink`，不存在则静默。"""
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
