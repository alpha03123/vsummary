from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.video_summary.adapters.plugin.bilibili.workspace import BilibiliPluginWorkspace
from backend.video_summary.adapters.plugin.bilibili.models import BilibiliPluginVideoKey, BilibiliPluginVideoMeta


class BilibiliPluginWorkspaceTests(unittest.TestCase):
    def test_uses_bvid_and_page_as_lightweight_output_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = BilibiliPluginWorkspace(Path(tmp))
            key = BilibiliPluginVideoKey(bvid="BV1xx411c7mD", page=2)

            output_dir = workspace.output_dir(key)

            self.assertEqual(output_dir, Path(tmp) / "workspace" / "plugin" / "bilibili" / "BV1xx411c7mD" / "p2")

    def test_saves_and_loads_lightweight_summary_without_media_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = BilibiliPluginWorkspace(Path(tmp))
            key = BilibiliPluginVideoKey(bvid="BV1xx411c7mD", page=1)
            meta = BilibiliPluginVideoMeta(
                bvid="BV1xx411c7mD",
                page=1,
                video_id="BV1xx411c7mD",
                title="第一讲",
                source_url="https://www.bilibili.com/video/BV1xx411c7mD",
                cover_url="https://example.test/cover.jpg",
                duration_seconds=123,
            )
            workspace.save_meta(meta)
            output_dir = workspace.output_dir(key)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "summary.json").write_text(json.dumps({"title": "第一讲"}), encoding="utf-8")

            result = workspace.get_summary(key)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.meta.title, "第一讲")
            self.assertEqual(result.summary, {"title": "第一讲"})

    def test_cleanup_temp_dir_removes_downloaded_media_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = BilibiliPluginWorkspace(Path(tmp))
            key = BilibiliPluginVideoKey(bvid="BV1xx411c7mD", page=1)
            temp_dir = workspace.temp_dir(key)
            temp_dir.mkdir(parents=True)
            (temp_dir / "BV1xx411c7mD.mp4").write_bytes(b"media")
            output_dir = workspace.output_dir(key)
            output_dir.mkdir(parents=True)
            (output_dir / "summary.json").write_text("{}", encoding="utf-8")

            workspace.cleanup_temp_dir(key)

            self.assertFalse(temp_dir.exists())
            self.assertTrue((output_dir / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
