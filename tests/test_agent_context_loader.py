from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.infrastructure.workspace_context_loader import WorkspaceAgentContextLoader
from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace


class AgentContextLoaderTests(unittest.TestCase):
    def test_loads_video_context_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "videos" / "series-a").mkdir(parents=True)
            (root / "workspace" / "series-a" / "intro").mkdir(parents=True)
            (root / "videos" / "series-a" / "intro.mp4").write_text("video", encoding="utf-8")
            (root / "workspace" / "series-a" / "intro" / "summary.json").write_text(
                json.dumps(
                    {
                        "title": "intro",
                        "chapters": [{"title": "第一章"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            loader = WorkspaceAgentContextLoader(FileSystemVideoWorkspace(root))
            context = loader.load("video|series-a|intro|overview")

            self.assertEqual(context.scope_type, "video")
            self.assertEqual(context.series_id, "series-a")
            self.assertEqual(context.video_id, "intro")
            self.assertEqual(context.selected_tool, "overview")
            self.assertTrue(context.overview.generated)
            self.assertFalse(context.mindmap.generated)
            self.assertTrue(context.notes.available)
            self.assertFalse(context.knowledge_cards.generated)
            self.assertEqual(context.chapter_titles, ["第一章"])

    def test_loads_series_context_when_video_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "videos" / "series-a").mkdir(parents=True)
            (root / "videos" / "series-a" / "intro.mp4").write_text("video", encoding="utf-8")

            loader = WorkspaceAgentContextLoader(FileSystemVideoWorkspace(root))
            context = loader.load("series|series-a|series-home")

            self.assertEqual(context.scope_type, "series")
            self.assertEqual(context.series_id, "series-a")
            self.assertEqual(context.selected_tool, "series-home")


if __name__ == "__main__":
    unittest.main()
