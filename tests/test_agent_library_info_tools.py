from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import GetVideoSummaryCall, GetVideoToolsCall
from backend.agent.tools.library_info import (
    create_get_video_summary_handler,
    create_get_video_tools_handler,
)
from backend.video_summary.library.views import (
    SeriesView,
    VideoCardView,
    WorkspaceToolView,
    WorkspaceView,
)


class FakeWorkspace:
    def get_workspace(self):
        return WorkspaceView(id="video-include", title="Video Include")

    def list_series(self):
        return [
            SeriesView(
                id="series-a",
                title="Series A",
                videos=[
                    VideoCardView(
                        id="video-1",
                        title="Video 1",
                        source_name="video-1.mp4",
                        processed=True,
                        status="ready",
                    )
                ],
            )
        ]

    def get_video_summary(self, series_id: str, video_id: str):
        raise AssertionError("series 级缺少 video_id 时不应继续读取 summary")

    def get_video_workspace_tools(self, series_id: str, video_id: str):
        raise AssertionError("series 级缺少 video_id 时不应继续读取 tools")


class AgentLibraryInfoToolTests(unittest.TestCase):
    def test_get_video_summary_returns_invalid_input_when_series_context_has_no_video(self) -> None:
        handler = create_get_video_summary_handler(FakeWorkspace())
        result = handler(
            GetVideoSummaryCall(tool_name="get_video_summary"),
            AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
                series_title="Series A",
                selected_tool="series-home",
            ),
        )

        self.assertEqual(result.status, "invalid_input")
        self.assertEqual(result.payload["series_id"], "series-a")
        self.assertEqual(result.payload["error"], "缺少 video_id，无法读取视频概况。")

    def test_get_video_tools_returns_invalid_input_when_series_context_has_no_video(self) -> None:
        handler = create_get_video_tools_handler(FakeWorkspace())
        result = handler(
            GetVideoToolsCall(tool_name="get_video_tools"),
            AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
                series_title="Series A",
                selected_tool="series-home",
            ),
        )

        self.assertEqual(result.status, "invalid_input")
        self.assertEqual(result.payload["series_id"], "series-a")
        self.assertEqual(result.payload["error"], "缺少 video_id，无法读取视频工具状态。")


if __name__ == "__main__":
    unittest.main()
