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

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import GetVideoTranscriptCall
from backend.agent.tools.library_info import create_get_video_transcript_handler
from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace


class AgentVideoTranscriptTests(unittest.TestCase):
    def test_get_video_transcript_returns_full_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "videos" / "series-a").mkdir(parents=True)
            (root / "workspace" / "series-a" / "video-1").mkdir(parents=True)
            (root / "videos" / "series-a" / "video-1.mp4").write_text("video", encoding="utf-8")
            (root / "workspace" / "series-a" / "video-1" / "transcript.cleaned.json").write_text(
                json.dumps(
                    {
                        "title": "video-1",
                        "duration_seconds": 146,
                        "segments": [
                            {
                                "start_seconds": 128,
                                "end_seconds": 146,
                                "text": "后续项目会用到百度地图 API，需要提前申请 API Key。",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            workspace = FileSystemVideoWorkspace(root)
            handler = create_get_video_transcript_handler(workspace)
            context = AgentContext(
                session_id="video|series-a|video-1|studio",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            )

            result = handler(
                GetVideoTranscriptCall(video_id="video-1"),
                context,
            )

            self.assertEqual(result.tool_name.value, "get_video_transcript")
            self.assertEqual(result.payload["video_id"], "video-1")
            self.assertEqual(result.payload["duration_seconds"], 146.0)
            self.assertEqual(
                result.payload["segments"],
                [
                    {
                        "start_seconds": 128.0,
                        "end_seconds": 146.0,
                        "text": "后续项目会用到百度地图 API，需要提前申请 API Key。",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
