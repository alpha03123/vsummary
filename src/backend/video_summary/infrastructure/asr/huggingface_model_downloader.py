"""HuggingFace 模型下载的统一封装（含续传、进度、校验、原子替换）。

业务场景：faster-whisper / whisper.cpp / RAG 都需要在用户机器上预下载大模型；
本类提供一份"下载 → 校验 → 原子替换"的统一流程：

1. 先把文件下载到 `.{target}.download/` 临时目录；
2. 单个文件先落到 `.incomplete/` 暂存区，完成并核对大小后才移入临时目录；
3. 校验必要文件/通配文件存在；
4. 校验通过后用 `Path.replace` 把临时目录替换为正式目录（原子）。

与早期实现的关键差异：**失败与取消都保留临时目录**。底层交给
`huggingface_hub.file_download.http_get`，它按 `resume_size` 发 `Range` 头续传，
并对连接中断做多次重试。保留现场才能让下一次下载从断点继续——旧实现在任何异常
下都删除整个临时目录，2GB 文件在末段断线会导致此前进度全部作废。
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from hashlib import sha1
from pathlib import Path
import shutil
from typing import Any

from backend.video_summary.generation.ports import ProgressReporter


_RESUME_DIR_NAME = ".incomplete"
_LOCAL_DIR_SIDECAR = ".cache"


@dataclass(frozen=True)
class HuggingFaceDownloadSpec:
    """单次下载任务所需的全部参数。

    Attributes:
        repo_id: HuggingFace 仓库 ID（`owner/name` 形式）。
        target_dir: 下载完成后落地的目标目录。
        required_files: 必须存在的具体文件名列表（缺失则报错）。
        required_file_patterns: 必须至少匹配一个的通配符列表（如 `tokenizer.*`）。
        allow_patterns: 限制下载范围的通配符；为空表示下载仓库全部文件。
        endpoint: 自定义 HuggingFace 镜像（对应 `HF_ENDPOINT` 环境变量）。
    """

    repo_id: str
    target_dir: Path
    required_files: tuple[str, ...]
    required_file_patterns: tuple[str, ...]
    allow_patterns: tuple[str, ...] = ()
    endpoint: str | None = None


class HuggingFaceDownloadCancelled(RuntimeError):
    """HuggingFace 模型下载被用户取消。"""


@dataclass(frozen=True)
class HuggingFaceCacheWarmSpec:
    """把仓库文件预热进标准 HF 缓存布局所需的参数。

    与 `HuggingFaceDownloadSpec` 的区别只在落盘形态：这里写的是
    `cache_dir/models--owner--name/{refs,blobs,snapshots}/`，因为消费方
    （fastembed）会用 `snapshot_download(local_files_only=True)` 反查这套布局，
    而不是读一个扁平目录。

    Attributes:
        repo_id: HuggingFace 仓库 ID。
        cache_dir: 缓存根目录（即传给 fastembed 的 `cache_dir`）。
        allow_patterns: 需要预热的文件通配符；必须与消费方自己的清单一致。
        endpoint: 自定义 HuggingFace 镜像（对应 `HF_ENDPOINT` 环境变量）。
    """

    repo_id: str
    cache_dir: Path
    allow_patterns: tuple[str, ...]
    endpoint: str | None = None


@dataclass(frozen=True)
class _FilePlan:
    """单个待下载文件的落盘计划。

    Attributes:
        filename: 仓库内的相对路径（可能含 `/`）。
        target_path: 临时目录中的最终位置。
        resume_path: `.incomplete/` 中的暂存文件位置。
        expected_size: 仓库元数据给出的字节数；未知时为 `None`。
        already_complete: 目标位置是否已存在且大小正确（跨次下载复用）。
    """

    filename: str
    target_path: Path
    resume_path: Path
    expected_size: int | None
    already_complete: bool


class HuggingFaceModelDownloader:
    """统一的 HuggingFace 模型下载器。

    进度上报通过传入的 `ProgressReporter` 完成：
    - `0%`：刚发起；
    - `5%-95%`：按已下载字节数线性映射（仓库未提供文件大小时不报百分比）；
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
            HuggingFaceDownloadCancelled: 用户取消；临时目录保留以便续传。
            Exception: 其他失败同样保留临时目录后原样上抛；常见的 `RuntimeError`
                来源于"校验时缺少必要文件"。
        """
        temp_dir = spec.target_dir.with_name(f".{spec.target_dir.name}.download")
        reporter.update("download", 0.0, f"正在连接模型仓库：{spec.repo_id}")
        _raise_if_download_cancelled(reporter)

        temp_dir.mkdir(parents=True, exist_ok=True)
        plans = self._snapshot_download(spec=spec, temp_dir=temp_dir, reporter=reporter)
        _raise_if_download_cancelled(reporter)

        reporter.update("validate", 95.0, f"正在校验模型文件：{spec.repo_id}")
        _validate_downloaded_model(temp_dir, spec)
        _prune_unexpected_entries(temp_dir, plans)
        _remove_path(spec.target_dir)
        temp_dir.replace(spec.target_dir)
        return spec.target_dir

    def _snapshot_download(
        self,
        *,
        spec: HuggingFaceDownloadSpec,
        temp_dir: Path,
        reporter: ProgressReporter,
    ) -> list[_FilePlan]:
        """按仓库文件清单逐个下载，支持断点续传并在字节流中响应取消。"""
        from huggingface_hub import HfApi

        api = HfApi(endpoint=spec.endpoint)
        model_info = api.model_info(spec.repo_id, files_metadata=True)
        files = _select_repo_files(model_info.siblings, spec.allow_patterns)
        if not files:
            raise RuntimeError(f"模型仓库未匹配到需要下载的文件：{spec.repo_id}")

        resume_dir = temp_dir / _RESUME_DIR_NAME
        resume_dir.mkdir(parents=True, exist_ok=True)
        plans = [_build_file_plan(file_info, temp_dir=temp_dir, resume_dir=resume_dir) for file_info in files]
        total_bytes = _sum_known_sizes(plans)
        downloaded_bytes = _sum_existing_bytes(plans)

        reporter.update(
            "download",
            _calculate_download_progress(downloaded_bytes, total_bytes),
            f"正在下载模型文件：{spec.repo_id}",
        )

        progress = _CancellableProgress(
            reporter=reporter,
            total=total_bytes,
            initial=downloaded_bytes,
        )
        for plan in plans:
            _raise_if_download_cancelled(reporter)
            if plan.already_complete:
                continue
            progress.set_current_file(plan.filename)
            _download_single_file(spec=spec, plan=plan, progress=progress)
        _raise_if_download_cancelled(reporter)
        return plans

    def warm_cache(self, spec: HuggingFaceCacheWarmSpec, reporter: ProgressReporter) -> Path:
        """把仓库文件预热进标准 HF 缓存布局，供 fastembed 之类的消费方离线复用。

        与 `download` 的差异：
        - 落盘形态是 `cache_dir/models--owner--name/{refs,blobs,snapshots}/`，
          直接交给 `hf_hub_download` 处理，不做临时目录 + 原子替换；
        - 取消粒度是"文件之间"而非字节流。预热的都是几十到几百 MB 的小文件，
          够用；`hf_hub_download` 自身留下的 `.incomplete` blob 会保留，
          下一次调用从断点继续。

        Args:
            spec: 预热任务参数。
            reporter: 用于上报进度与响应取消的 reporter。

        Returns:
            `cache_dir/models--owner--name` 目录路径。

        Raises:
            HuggingFaceDownloadCancelled: 用户取消；已下载的 blob 与 `.incomplete`
                均保留以便续传。
            RuntimeError: `allow_patterns` 在仓库里没匹配到任何文件。
        """
        from huggingface_hub import HfApi, hf_hub_download

        reporter.update("download", 0.0, f"正在连接模型仓库：{spec.repo_id}")
        _raise_if_download_cancelled(reporter)

        api = HfApi(endpoint=spec.endpoint)
        model_info = api.model_info(spec.repo_id, files_metadata=True)
        files = _select_repo_files(model_info.siblings, spec.allow_patterns)
        if not files:
            raise RuntimeError(f"模型仓库未匹配到需要下载的文件：{spec.repo_id}")

        sizes = [_file_size(file_info) for file_info in files]
        total_bytes = sum(size for size in sizes if size is not None) or None
        downloaded_bytes = 0

        spec.cache_dir.mkdir(parents=True, exist_ok=True)
        for file_info, size in zip(files, sizes):
            _raise_if_download_cancelled(reporter)
            reporter.update(
                "download",
                _calculate_download_progress(downloaded_bytes, total_bytes),
                f"正在下载模型文件：{file_info.rfilename}",
            )
            hf_hub_download(
                repo_id=spec.repo_id,
                filename=file_info.rfilename,
                cache_dir=str(spec.cache_dir),
                endpoint=spec.endpoint,
            )
            downloaded_bytes += size or 0

        _raise_if_download_cancelled(reporter)
        reporter.update("download", 95.0, f"模型文件已就绪：{spec.repo_id}")
        return spec.cache_dir / f"models--{spec.repo_id.replace('/', '--')}"


def _download_single_file(
    *,
    spec: HuggingFaceDownloadSpec,
    plan: _FilePlan,
    progress: _CancellableProgress,
) -> None:
    """把单个仓库文件续传到 `.incomplete/`，核对大小后移入临时目录。"""
    from huggingface_hub import hf_hub_url
    from huggingface_hub.utils import build_hf_headers

    url = hf_hub_url(spec.repo_id, plan.filename, endpoint=spec.endpoint)
    headers = build_hf_headers()
    plan.target_path.parent.mkdir(parents=True, exist_ok=True)
    plan.resume_path.parent.mkdir(parents=True, exist_ok=True)

    if plan.expected_size is not None and _path_size(plan.resume_path) > plan.expected_size:
        # 暂存文件比预期还大，说明上次留下的是脏数据，重下这一个文件。
        _remove_path(plan.resume_path)

    _stream_to_resume_file(spec=spec, url=url, headers=headers, plan=plan, progress=progress)

    actual_size = _path_size(plan.resume_path)
    if plan.expected_size is not None and actual_size != plan.expected_size:
        raise RuntimeError(
            f"模型文件下载不完整：{plan.filename}，期望 {plan.expected_size} bytes，实际 {actual_size} bytes"
        )
    _remove_path(plan.target_path)
    plan.resume_path.replace(plan.target_path)


def _stream_to_resume_file(
    *,
    spec: HuggingFaceDownloadSpec,
    url: str,
    headers: dict[str, str],
    plan: _FilePlan,
    progress: _CancellableProgress,
) -> None:
    """调用 huggingface_hub 的 `http_get` 续传写入暂存文件。

    `http_get` 提供三项本模块依赖的能力：`resume_size` 决定 `Range` 头、
    `_tqdm_bar` 透出字节级进度（也是取消的注入点）、内部对连接中断重试。
    这两个参数带下划线前缀，属于半公开 API；`_supports_byte_progress` 做特性
    探测，签名变化时退回 `_fallback_download`。
    """
    from huggingface_hub.file_download import http_get

    if not _supports_byte_progress():
        _fallback_download(spec=spec, plan=plan, progress=progress)
        return

    with plan.resume_path.open("ab") as output:
        resume_size = output.tell()
        if plan.expected_size is not None and resume_size == plan.expected_size:
            return
        http_get(
            url,
            output,
            headers=headers,
            resume_size=resume_size,
            expected_size=plan.expected_size,
            displayed_filename=plan.filename,
            _tqdm_bar=progress,
        )


def _fallback_download(
    *,
    spec: HuggingFaceDownloadSpec,
    plan: _FilePlan,
    progress: _CancellableProgress,
) -> None:
    """`http_get` 签名不兼容时的退路：改用公开的 `hf_hub_download`。

    仍然保留续传与重试（`hf_hub_download` 内部同样走 `.incomplete` + `Range`），
    但失去字节级进度与文件内取消：整个文件下载完成后才一次性计入进度，取消只能
    在文件边界生效。
    """
    from huggingface_hub import hf_hub_download

    scratch_dir = plan.resume_path.parent / f"{plan.resume_path.name}.hfdl"
    downloaded = hf_hub_download(
        repo_id=spec.repo_id,
        filename=plan.filename,
        endpoint=spec.endpoint,
        local_dir=str(scratch_dir),
    )
    Path(downloaded).replace(plan.resume_path)
    _remove_path(scratch_dir)
    progress.update(_path_size(plan.resume_path) - progress.counted_for_current_file)


def _supports_byte_progress() -> bool:
    """探测 `http_get` 是否仍接受 `resume_size` 与 `_tqdm_bar`。"""
    import inspect

    from huggingface_hub.file_download import http_get

    parameters = inspect.signature(http_get).parameters
    return "resume_size" in parameters and "_tqdm_bar" in parameters


class _CancellableProgress:
    """`http_get` 的 `_tqdm_bar` 替身：把字节增量转成业务进度并响应取消。

    `huggingface_hub` 在 `_get_progress_bar_context` 里对传入的 bar 直接
    `nullcontext` 包装，随后只调用 `.update(n)`（见 `file_download.py` 的
    `progress.update` 调用点），因此这里无需实现完整 tqdm 接口。

    `update()` 在 `http_get` 写盘之前被调用，所以取消时当前 chunk 不会落盘；
    已落盘的字节保持不变，下次按暂存文件实际大小续传，计数自动对齐。
    """

    def __init__(self, *, reporter: ProgressReporter, total: int | None, initial: int) -> None:
        self._reporter = reporter
        self._total = total
        self._downloaded = initial
        self._filename = ""
        self._counted_for_current_file = 0

    @property
    def counted_for_current_file(self) -> int:
        """当前文件已计入总进度的字节数（`_fallback_download` 用它补齐差额）。"""
        return self._counted_for_current_file

    def set_current_file(self, filename: str) -> None:
        """切换当前文件名并重置该文件的计数，用于进度文案与补差。"""
        self._filename = filename
        self._counted_for_current_file = 0

    def update(self, n: int | float = 1) -> bool:
        """累计字节增量、上报进度，并在取消时抛出异常中断 `http_get`。"""
        if n:
            self._downloaded += int(n)
            self._counted_for_current_file += int(n)
        self._reporter.update(
            "download",
            _calculate_download_progress(self._downloaded, self._total),
            f"正在下载模型文件：{self._filename}",
        )
        _raise_if_download_cancelled(self._reporter)
        return True

    def close(self) -> None:
        """兼容可能的 tqdm 生命周期调用。"""
        return None


def _raise_if_download_cancelled(reporter: ProgressReporter) -> None:
    """把通用 reporter 取消信号转换为下载器专用异常。"""
    if reporter.is_cancel_requested():
        raise HuggingFaceDownloadCancelled("模型下载已取消")
    try:
        reporter.raise_if_cancelled()
    except HuggingFaceDownloadCancelled:
        raise
    except RuntimeError as error:
        if "取消" in str(error):
            raise HuggingFaceDownloadCancelled("模型下载已取消") from error
        raise


def _build_file_plan(file_info: Any, *, temp_dir: Path, resume_dir: Path) -> _FilePlan:
    """把仓库文件元数据转成落盘计划，并判断是否已在上次下载中完成。"""
    filename = str(file_info.rfilename)
    target_path = temp_dir / filename
    expected_size = _file_size(file_info)
    already_complete = target_path.is_file() and (
        expected_size is None or target_path.stat().st_size == expected_size
    )
    return _FilePlan(
        filename=filename,
        target_path=target_path,
        resume_path=resume_dir / _resume_file_name(filename),
        expected_size=expected_size,
        already_complete=already_complete,
    )


def _resume_file_name(filename: str) -> str:
    """为可能含 `/` 的仓库路径生成扁平且稳定的暂存文件名。"""
    digest = sha1(filename.encode("utf-8")).hexdigest()[:16]
    return f"{digest}-{Path(filename).name}.part"


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


def _sum_known_sizes(plans: list[_FilePlan]) -> int | None:
    """汇总计划中的文件大小；任一文件缺少 size 时返回 None（进度改为不确定）。"""
    if any(plan.expected_size is None for plan in plans):
        return None
    return sum(plan.expected_size or 0 for plan in plans)


def _sum_existing_bytes(plans: list[_FilePlan]) -> int:
    """统计本次开始前已在磁盘上的字节数（已完成文件 + 暂存片段）。"""
    total = 0
    for plan in plans:
        if plan.already_complete:
            total += plan.expected_size if plan.expected_size is not None else _path_size(plan.target_path)
            continue
        total += _path_size(plan.resume_path)
    return total


def _file_size(file_info: Any) -> int | None:
    """读取 HuggingFace sibling 的文件大小，兼容不同版本字段。"""
    size = getattr(file_info, "size", None)
    if isinstance(size, int):
        return size
    lfs = getattr(file_info, "lfs", None)
    if isinstance(lfs, dict) and isinstance(lfs.get("size"), int):
        return lfs["size"]
    return None


def _path_size(path: Path) -> int:
    """返回文件字节数；不存在时返回 0。"""
    return path.stat().st_size if path.is_file() else 0


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


def _prune_unexpected_entries(temp_dir: Path, plans: list[_FilePlan]) -> None:
    """原子替换前清掉暂存区与历史残留，避免它们被带进正式目录。

    需要清理的两类内容：
        1. `.incomplete/` 暂存区与 `hf_hub_download(local_dir=...)` 留下的 `.cache/`；
        2. 上一次 `allow_patterns` 更宽时下载、本次计划中已不存在的文件。
    """
    _remove_path(temp_dir / _RESUME_DIR_NAME)
    _remove_path(temp_dir / _LOCAL_DIR_SIDECAR)
    expected = {plan.target_path.resolve() for plan in plans}
    for path in sorted(temp_dir.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file() and path.resolve() not in expected:
            _remove_path(path)
        elif path.is_dir() and not any(path.iterdir()):
            _remove_path(path)


def _remove_path(path: Path) -> None:
    """删除文件或目录：目录用 `shutil.rmtree`，文件用 `unlink`，不存在则静默。"""
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
