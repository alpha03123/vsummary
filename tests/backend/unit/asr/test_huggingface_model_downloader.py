"""`HuggingFaceModelDownloader` 的下载/续传/取消语义测试。

这些测试全部在 `huggingface_hub.file_download.http_get` 这一层打桩，不发真实网络
请求：真实 `http_get` 的关键契约（`resume_size` 决定 `Range` 偏移、`_tqdm_bar.update(n)`
在写盘之前被调用）由 `_FakeHttpGet` 精确复刻，因此取消时"当前 chunk 不落盘"这一
语义可以被真正验证。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.video_summary.infrastructure.asr.huggingface_model_downloader import (
    HuggingFaceDownloadCancelled,
    HuggingFaceDownloadSpec,
    HuggingFaceModelDownloader,
)


_CHUNK = 10


class _Reporter:
    """在第 `cancel_after_updates` 次进度回调时请求取消的测试用 reporter。"""

    def __init__(self, *, cancel_after_updates: int | None = None) -> None:
        self.cancel_after_updates = cancel_after_updates
        self.update_calls = 0
        self.cancel_requested = False
        self.progress_values: list[float | None] = []
        self.completed_detail: str | None = None
        self.failure: str | None = None

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        del stage, detail
        self.update_calls += 1
        self.progress_values.append(progress)
        if self.cancel_after_updates is not None and self.update_calls >= self.cancel_after_updates:
            self.cancel_requested = True

    def completed(self, detail: str | None = None) -> None:
        self.completed_detail = detail

    def failed(self, message: str) -> None:
        self.failure = message

    def cancelled(self, detail: str | None = None) -> None:
        del detail

    def is_cancel_requested(self) -> bool:
        return self.cancel_requested

    def raise_if_cancelled(self) -> None:
        if self.cancel_requested:
            raise RuntimeError("任务已取消")


class _FakeHttpGet:
    """复刻真实 `http_get` 的签名与"先 update 再 write"的调用顺序。

    签名必须保留 `resume_size` 与 `_tqdm_bar`，否则被测代码的
    `_supports_byte_progress()` 特性探测会判定不支持并走 fallback 分支。
    """

    def __init__(self, contents: dict[str, bytes]) -> None:
        self._contents = contents
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        url: str,
        temp_file,
        *,
        proxies=None,
        resume_size: int = 0,
        headers=None,
        expected_size: int | None = None,
        displayed_filename: str | None = None,
        _nb_retries: int = 5,
        _tqdm_bar=None,
    ) -> None:
        del proxies, headers, expected_size, _nb_retries
        filename = displayed_filename or ""
        self.calls.append({"url": url, "filename": filename, "resume_size": resume_size})
        payload = self._contents[filename][resume_size:]
        for offset in range(0, len(payload), _CHUNK):
            chunk = payload[offset : offset + _CHUNK]
            if _tqdm_bar is not None:
                # 真实 http_get 在写盘之前调用 update，取消因此能丢弃当前 chunk。
                _tqdm_bar.update(len(chunk))
            temp_file.write(chunk)
            temp_file.flush()


def _install_fakes(monkeypatch, *, siblings: list[SimpleNamespace], contents: dict[str, bytes]) -> _FakeHttpGet:
    """打桩 `HfApi.model_info` 与 `http_get`，返回可断言调用参数的假 `http_get`。"""

    class FakeHfApi:
        def __init__(self, endpoint=None) -> None:
            self.endpoint = endpoint

        def model_info(self, repo_id, files_metadata=False):
            del repo_id, files_metadata
            return SimpleNamespace(siblings=siblings)

    fake_http_get = _FakeHttpGet(contents)
    monkeypatch.setattr("huggingface_hub.HfApi", FakeHfApi)
    monkeypatch.setattr("huggingface_hub.file_download.http_get", fake_http_get)
    return fake_http_get


def _make_spec(target_dir: Path, **overrides) -> HuggingFaceDownloadSpec:
    defaults = {
        "repo_id": "owner/model",
        "target_dir": target_dir,
        "required_files": ("model.bin", "config.json"),
        "required_file_patterns": (),
    }
    defaults.update(overrides)
    return HuggingFaceDownloadSpec(**defaults)


def _siblings() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(rfilename="model.bin", size=100),
        SimpleNamespace(rfilename="config.json", size=20),
    ]


def _contents() -> dict[str, bytes]:
    return {"model.bin": b"m" * 100, "config.json": b"c" * 20}


def test_successful_download_replaces_target_and_prunes_scratch(monkeypatch, tmp_path: Path) -> None:
    """成功路径：文件落到正式目录，暂存区与 sidecar 不被带入。"""
    reporter = _Reporter()
    _install_fakes(monkeypatch, siblings=_siblings(), contents=_contents())
    target_dir = tmp_path / "model"

    result = HuggingFaceModelDownloader().download(_make_spec(target_dir), reporter)

    assert result == target_dir
    assert (target_dir / "model.bin").read_bytes() == b"m" * 100
    assert (target_dir / "config.json").read_bytes() == b"c" * 20
    assert not (target_dir / ".incomplete").exists()
    assert not (target_dir / ".cache").exists()
    assert not target_dir.with_name(".model.download").exists()


def test_cancel_preserves_temp_dir_and_partial_bytes(monkeypatch, tmp_path: Path) -> None:
    """取消时保留临时目录与已落盘字节，这是续传的前提。

    旧实现在任何异常下都删除临时目录，导致大文件末段断线后进度全部作废；
    本测试锁定新语义：临时目录必须存活，且当前 chunk 不落盘。
    """
    # update() 调用序列：#1 连接仓库（0%）、#2 计划建立后的初始上报，
    # 之后第 N 个 chunk 对应第 N+2 次调用。阈值 5 → 在第 3 个 chunk 的
    # update 中触发取消，因此前 2 个 chunk 已落盘、第 3 个被拦下。
    reporter = _Reporter(cancel_after_updates=5)
    _install_fakes(monkeypatch, siblings=_siblings(), contents=_contents())
    target_dir = tmp_path / "model"
    temp_dir = target_dir.with_name(".model.download")

    with pytest.raises(HuggingFaceDownloadCancelled):
        HuggingFaceModelDownloader().download(_make_spec(target_dir), reporter)

    assert not target_dir.exists()
    assert temp_dir.is_dir(), "临时目录必须保留，否则无法续传"
    partials = list((temp_dir / ".incomplete").glob("*.part"))
    assert len(partials) == 1
    # 触发取消的那个 chunk 在写盘前被拦下，因此只剩前两个 chunk。
    assert partials[0].stat().st_size == 2 * _CHUNK


def test_second_attempt_resumes_from_partial_bytes(monkeypatch, tmp_path: Path) -> None:
    """取消后再次下载：`resume_size` 必须等于已落盘字节数。"""
    target_dir = tmp_path / "model"
    temp_dir = target_dir.with_name(".model.download")

    first_reporter = _Reporter(cancel_after_updates=5)
    _install_fakes(monkeypatch, siblings=_siblings(), contents=_contents())
    with pytest.raises(HuggingFaceDownloadCancelled):
        HuggingFaceModelDownloader().download(_make_spec(target_dir), first_reporter)
    partial_size = next((temp_dir / ".incomplete").glob("*.part")).stat().st_size

    second_reporter = _Reporter()
    fake_http_get = _install_fakes(monkeypatch, siblings=_siblings(), contents=_contents())
    HuggingFaceModelDownloader().download(_make_spec(target_dir), second_reporter)

    model_calls = [call for call in fake_http_get.calls if call["filename"] == "model.bin"]
    assert len(model_calls) == 1
    assert model_calls[0]["resume_size"] == partial_size, "续传必须从断点开始，而非从 0 重下"
    assert (target_dir / "model.bin").read_bytes() == b"m" * 100


def test_already_complete_file_is_not_redownloaded(monkeypatch, tmp_path: Path) -> None:
    """临时目录里已完整的文件跳过网络请求。"""
    target_dir = tmp_path / "model"
    temp_dir = target_dir.with_name(".model.download")
    temp_dir.mkdir(parents=True)
    (temp_dir / "model.bin").write_bytes(b"m" * 100)

    reporter = _Reporter()
    fake_http_get = _install_fakes(monkeypatch, siblings=_siblings(), contents=_contents())
    HuggingFaceModelDownloader().download(_make_spec(target_dir), reporter)

    requested = {call["filename"] for call in fake_http_get.calls}
    assert requested == {"config.json"}, "已完成的 model.bin 不应再次下载"


def test_size_mismatch_raises_and_keeps_temp_dir(monkeypatch, tmp_path: Path) -> None:
    """服务端返回字节数与元数据不符时报错，且保留临时目录。"""
    reporter = _Reporter()
    # 元数据声明 100 字节，实际只给 40 字节。
    _install_fakes(
        monkeypatch,
        siblings=_siblings(),
        contents={"model.bin": b"m" * 40, "config.json": b"c" * 20},
    )
    target_dir = tmp_path / "model"

    with pytest.raises(RuntimeError, match="下载不完整"):
        HuggingFaceModelDownloader().download(_make_spec(target_dir), reporter)

    assert not target_dir.exists()
    assert target_dir.with_name(".model.download").is_dir()


def test_missing_required_file_raises_and_keeps_temp_dir(monkeypatch, tmp_path: Path) -> None:
    """仓库缺少 required_files 时校验失败，临时目录保留供排查。"""
    reporter = _Reporter()
    _install_fakes(
        monkeypatch,
        siblings=[SimpleNamespace(rfilename="config.json", size=20)],
        contents={"config.json": b"c" * 20},
    )
    target_dir = tmp_path / "model"

    with pytest.raises(RuntimeError, match="缺少必要文件"):
        HuggingFaceModelDownloader().download(_make_spec(target_dir), reporter)

    assert not target_dir.exists()
    assert target_dir.with_name(".model.download").is_dir()


def test_allow_patterns_filter_repo_files(monkeypatch, tmp_path: Path) -> None:
    """`allow_patterns` 限制下载范围，未命中的文件不请求也不落盘。"""
    reporter = _Reporter()
    fake_http_get = _install_fakes(
        monkeypatch,
        siblings=[
            SimpleNamespace(rfilename="ggml-small.bin", size=30),
            SimpleNamespace(rfilename="ggml-large.bin", size=40),
        ],
        contents={"ggml-small.bin": b"s" * 30, "ggml-large.bin": b"l" * 40},
    )
    target_dir = tmp_path / "whisper"

    HuggingFaceModelDownloader().download(
        _make_spec(
            target_dir,
            required_files=("ggml-small.bin",),
            allow_patterns=("ggml-small.bin",),
        ),
        reporter,
    )

    assert {call["filename"] for call in fake_http_get.calls} == {"ggml-small.bin"}
    assert not (target_dir / "ggml-large.bin").exists()


def test_no_matching_repo_file_raises(monkeypatch, tmp_path: Path) -> None:
    """`allow_patterns` 未命中任何仓库文件时给出明确错误。"""
    reporter = _Reporter()
    _install_fakes(
        monkeypatch,
        siblings=[SimpleNamespace(rfilename="ggml-large.bin", size=40)],
        contents={"ggml-large.bin": b"l" * 40},
    )

    with pytest.raises(RuntimeError, match="未匹配到需要下载的文件"):
        HuggingFaceModelDownloader().download(
            _make_spec(
                tmp_path / "whisper",
                required_files=("ggml-small.bin",),
                allow_patterns=("ggml-small.bin",),
            ),
            reporter,
        )


def test_progress_is_monotonic_within_download_band(monkeypatch, tmp_path: Path) -> None:
    """下载阶段进度落在 5%-95% 区间且单调不减。"""
    reporter = _Reporter()
    _install_fakes(monkeypatch, siblings=_siblings(), contents=_contents())

    HuggingFaceModelDownloader().download(_make_spec(tmp_path / "model"), reporter)

    # 首次上报是"正在连接仓库"的 0%，按设计位于下载区间之外，断言时排除。
    assert reporter.progress_values[0] == 0.0
    band = [value for value in reporter.progress_values[1:] if value is not None]
    assert band, "应至少上报一次下载阶段进度"
    assert all(5.0 <= value <= 95.0 for value in band)
    assert band == sorted(band), "进度不应回退"
