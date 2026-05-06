from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests import _path_setup  # noqa: F401

from backend.video_summary.infrastructure.huggingface_model_downloader import (
    HuggingFaceDownloadSpec,
    HuggingFaceModelDownloader,
)
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker


class HuggingFaceModelDownloaderTests(unittest.TestCase):
    def test_download_reports_intermediate_progress_from_tqdm_updates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            tracker = InMemoryProgressTracker()
            reporter = tracker.create_reporter("download/model")

            def snapshot_download(**kwargs) -> None:
                progress = kwargs["tqdm_class"](total=100, desc="model.bin")
                progress.update(40)
                progress.close()
                local_dir = Path(kwargs["local_dir"])
                (local_dir / "config.json").write_text("{}", encoding="utf-8")
                (local_dir / "model.bin").write_text("model", encoding="utf-8")

            downloader = HuggingFaceModelDownloader(
                snapshot_download=snapshot_download,
                model_info_loader=lambda repo_id, endpoint: _model_info(("config.json", 10), ("model.bin", 90)),
            )

            downloader.download(
                HuggingFaceDownloadSpec(
                    repo_id="example/model",
                    target_dir=root_dir / "model",
                    required_files=("config.json", "model.bin"),
                    required_file_patterns=(),
                ),
                reporter,
            )

            snapshot = tracker.get_snapshot("download/model")
            self.assertEqual(snapshot.status, "running")
            self.assertEqual(snapshot.stage, "validate")
            self.assertGreater(snapshot.progress or 0, 0)
            self.assertLess(snapshot.progress or 100, 100)

    def test_cancel_removes_temporary_directory_without_replacing_existing_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            target_dir = root_dir / "model"
            target_dir.mkdir()
            (target_dir / "config.json").write_text("old", encoding="utf-8")
            (target_dir / "model.bin").write_text("old", encoding="utf-8")

            tracker = InMemoryProgressTracker()
            reporter = tracker.create_reporter("download/model")
            tracker.request_cancel("download/model")

            def snapshot_download(**kwargs) -> None:
                progress = kwargs["tqdm_class"](total=100, desc="model.bin")
                progress.update(1)

            downloader = HuggingFaceModelDownloader(
                snapshot_download=snapshot_download,
                model_info_loader=lambda repo_id, endpoint: _model_info(("model.bin", 100)),
            )

            with self.assertRaises(RuntimeError):
                downloader.download(
                    HuggingFaceDownloadSpec(
                        repo_id="example/model",
                        target_dir=target_dir,
                        required_files=("config.json", "model.bin"),
                        required_file_patterns=(),
                    ),
                    reporter,
                )

            self.assertFalse((root_dir / ".model.download").exists())
            self.assertEqual((target_dir / "model.bin").read_text(encoding="utf-8"), "old")

    def test_cancelled_task_can_create_new_reporter_for_retry(self) -> None:
        tracker = InMemoryProgressTracker()
        first = tracker.create_reporter("download/model")
        tracker.request_cancel("download/model")
        first.cancelled("cancelled")

        second = tracker.create_reporter("download/model")

        self.assertFalse(second.is_cancel_requested())
        self.assertEqual(tracker.get_snapshot("download/model").status, "running")


def _model_info(*files: tuple[str, int]):
    return SimpleNamespace(
        siblings=[
            SimpleNamespace(rfilename=file_name, size=size)
            for file_name, size in files
        ]
    )


if __name__ == "__main__":
    unittest.main()
