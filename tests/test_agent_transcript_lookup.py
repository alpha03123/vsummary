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

from backend.agent.infrastructure.transcript_lookup import WorkspaceTranscriptLookup
from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import TranscriptLookupCall
from backend.agent.tools.transcript import create_transcript_lookup_handler
from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace


class AgentTranscriptLookupTests(unittest.TestCase):
    def test_lookup_returns_seekable_transcript_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "videos" / "series-a").mkdir(parents=True)
            (root / "workspace" / "series-a" / "video-1").mkdir(parents=True)
            (root / "videos" / "series-a" / "video-1.mp4").write_text("video", encoding="utf-8")
            (root / "workspace" / "series-a" / "video-1" / "summary.json").write_text(
                json.dumps(
                    {
                        "title": "video-1",
                        "chapters": [
                            {
                                "id": "chapter-1",
                                "title": "准备工作",
                                "summary": "介绍百度地图 API Key 的申请准备。",
                                "key_points": ["需要提前申请 API Key"],
                                "start_seconds": 120,
                                "end_seconds": 210,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "workspace" / "series-a" / "video-1" / "transcript.cleaned.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "start_seconds": 128,
                                "end_seconds": 146,
                                "text": "后续项目会用到百度地图 API，需要提前申请 API Key。",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            workspace = FileSystemVideoWorkspace(root)
            lookup = WorkspaceTranscriptLookup(workspace)
            handler = create_transcript_lookup_handler(lookup)
            context = AgentContext(
                session_id="video|series-a|video-1|studio",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            )

            result = handler(TranscriptLookupCall(query="百度地图 API Key"), context)

            self.assertEqual(result.payload["selected_tool"], "video")
            self.assertEqual(result.payload["seek_seconds"], 128.0)
            self.assertEqual(result.payload["chapter_title"], "准备工作")
            self.assertTrue(result.payload["matches"])


if __name__ == "__main__":
    unittest.main()
