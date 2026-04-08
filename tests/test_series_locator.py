from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.runtime.series_locator import SERIES_LOCATOR_SYSTEM_PROMPT, select_series_locate_candidates
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class _SeriesLocatorGateway:
    def __init__(self, response: str) -> None:
        self._response = response

    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion_stream(self, messages):
        del messages
        yield ""

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        assert SERIES_LOCATOR_SYSTEM_PROMPT in messages[0].content
        return self._response


class SeriesLocatorTests(unittest.TestCase):
    def test_select_series_locate_candidates_returns_ranked_video_ids(self) -> None:
        decision = select_series_locate_candidates(
            gateway=_SeriesLocatorGateway('{"video_ids":["video-2","video-3"],"reason":"video-2 最相关，video-3 次之。"}'),
            user_message="这个系列里哪里讲过 Nacos 3？",
            summary_results=[
                ToolExecutionResult(
                    tool_name=ToolName.GET_VIDEO_SUMMARY,
                    status="ok",
                    payload={"video_id": "video-1", "title": "Video 1"},
                ),
                ToolExecutionResult(
                    tool_name=ToolName.GET_VIDEO_SUMMARY,
                    status="ok",
                    payload={"video_id": "video-2", "title": "Video 2"},
                ),
            ],
        )

        self.assertEqual(decision.video_ids, ["video-2", "video-3"])


if __name__ == "__main__":
    unittest.main()
