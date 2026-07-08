from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.video_summary.infrastructure.asr.huggingface_model_downloader import (
    HuggingFaceDownloadCancelled,
    HuggingFaceDownloadSpec,
    HuggingFaceModelDownloader,
)


class _Reporter:
    def __init__(self) -> None:
        self.cancel_requested = False
        self.updated = False

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        del stage, progress
        self.updated = True
        if detail == "正在下载模型文件：model.bin":
            self.cancel_requested = True

    def completed(self, detail: str | None = None) -> None:
        pass

    def failed(self, message: str) -> None:
        pass

    def cancelled(self, detail: str | None = None) -> None:
        pass

    def is_cancel_requested(self) -> bool:
        return self.cancel_requested

    def raise_if_cancelled(self) -> None:
        if self.cancel_requested:
            raise RuntimeError("任务已取消")


def test_chunk_download_cancel_cleans_temp_dir(monkeypatch, tmp_path: Path) -> None:
    reporter = _Reporter()

    class FakeHfApi:
        def __init__(self, endpoint=None) -> None:
            self.endpoint = endpoint

        def model_info(self, repo_id, files_metadata=False):
            del repo_id, files_metadata
            return SimpleNamespace(
                siblings=[
                    SimpleNamespace(rfilename="model.bin", size=100),
                    SimpleNamespace(rfilename="config.json", size=2),
                ],
            )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def iter_content(self, chunk_size):
            del chunk_size
            yield b"partial"

    class FakeSession:
        def get(self, *args, **kwargs):
            del args, kwargs
            return FakeResponse()

    monkeypatch.setattr("huggingface_hub.HfApi", FakeHfApi)
    monkeypatch.setattr("huggingface_hub.utils.get_session", lambda: FakeSession())
    monkeypatch.setattr("huggingface_hub.utils.hf_raise_for_status", lambda response: None)

    target_dir = tmp_path / "model"
    downloader = HuggingFaceModelDownloader()
    spec = HuggingFaceDownloadSpec(
        repo_id="owner/model",
        target_dir=target_dir,
        required_files=("model.bin", "config.json"),
        required_file_patterns=(),
    )

    with pytest.raises(HuggingFaceDownloadCancelled):
        downloader.download(spec, reporter)

    assert not target_dir.exists()
    assert not target_dir.with_name(".model.download").exists()
