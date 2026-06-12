from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from backend.video_summary.adapters.progress.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.workspace.linked_models import LinkedVideo
from backend.video_summary.adapters.plugin.bilibili.summary_service import BilibiliPluginSummaryService
from backend.video_summary.adapters.plugin.bilibili.workspace import BilibiliPluginWorkspace
from backend.video_summary.adapters.plugin.bilibili.models import BilibiliPluginVideoKey


class BilibiliPluginSummaryServiceTests(unittest.TestCase):
    def test_generates_summary_from_temp_media_and_removes_media_after_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = BilibiliPluginWorkspace(Path(tmp))
            tracker = InMemoryProgressTracker()
            downloader = _FakeDownloader()
            workflow = _FakeWorkflow()
            service = BilibiliPluginSummaryService(
                workspace=workspace,
                resolver=_FakeResolver(),
                downloader=downloader,
                workflow=workflow,
                progress_tracker=tracker,
            )

            result = asyncio.run(service.run(url="https://www.bilibili.com/video/BV1xx411c7mD?p=2"))

            key = BilibiliPluginVideoKey(bvid="BV1xx411c7mD", page=2)
            self.assertEqual(result.key, key)
            self.assertEqual(result.summary, {"title": "第二讲"})
            self.assertEqual(downloader.dest_dirs, [workspace.temp_dir(key)])
            self.assertEqual(workflow.source_paths, [workspace.temp_dir(key) / "BV1xx411c7mD_p2.mp4"])
            self.assertFalse(workspace.temp_dir(key).exists())
            self.assertTrue((workspace.output_dir(key) / "summary.json").exists())
            self.assertEqual(tracker.get_snapshot("plugin/bilibili/BV1xx411c7mD/p2").status, "completed")


class _FakeResolver:
    async def resolve_single_video(self, url_info):
        del url_info
        return LinkedVideo(
            bvid="BV1xx411c7mD",
            page=2,
            title="第二讲",
            cover_url="https://example.test/cover.jpg",
            duration_seconds=123,
            source_url="https://www.bilibili.com/video/BV1xx411c7mD?p=2",
        )


class _FakeDownloader:
    def __init__(self) -> None:
        self.dest_dirs: list[Path] = []

    async def download_async(self, bvid: str, page: int, dest_dir: Path, reporter) -> Path:
        del reporter
        self.dest_dirs.append(dest_dir)
        dest_dir.mkdir(parents=True)
        media_path = dest_dir / (bvid if page == 1 else f"{bvid}_p{page}").__add__(".mp4")
        media_path.write_bytes(b"media")
        return media_path


class _FakeWorkflow:
    def __init__(self) -> None:
        self.source_paths: list[Path] = []

    async def run(self, source_path: Path, output_dir: Path, progress_reporter=None, transcript_enhancement_enabled=None) -> None:
        del progress_reporter, transcript_enhancement_enabled
        self.source_paths.append(source_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "summary.json").write_text('{"title": "第二讲"}', encoding="utf-8")
        (output_dir / "summary.md").write_text("# 第二讲", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
