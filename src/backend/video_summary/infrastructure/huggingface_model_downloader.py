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
        """封装 `huggingface_hub.snapshot_download` 调用，传入 `endpoint` / `allow_patterns` 等可选参数。"""
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
