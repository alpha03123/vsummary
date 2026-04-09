from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext
from backend.agent.runtime.planner import (
    PLANNER_TRANSPORT_STREAM_BUFFERED,
    generate_execution_plan,
)
from backend.agent.schemas.messages import AgentChatMessage


class _StreamOnlyGateway:
    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise AssertionError("stream_buffered 模式不应走 structured completion")

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        del messages
        raise AssertionError("stream_buffered 模式拿到了流式输出时不应回退到普通 completion")

    def create_text_completion_stream(self, messages: list[AgentChatMessage]):
        del messages
        payload = '{"scope_type":"video","tool_calls":[{"tool_name":"get_video_tools","video_id":"video-1"}],"reason":"读取视频工具状态。","direct_response":"","use_answerer":false}'
        yield payload


class _EmptyStreamGateway:
    def __init__(self) -> None:
        self.fallback_called = False

    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise AssertionError("stream_buffered 模式不应走 structured completion")

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        del messages
        self.fallback_called = True
        return '{"scope_type":"video","tool_calls":[],"reason":"直接回复。","direct_response":"ok","use_answerer":false}'

    def create_text_completion_stream(self, messages: list[AgentChatMessage]):
        del messages
        if False:
            yield ""


class PlannerTransportTests(unittest.TestCase):
    def test_stream_buffered_transport_collects_stream_before_validation(self) -> None:
        plan = generate_execution_plan(
            gateway=_StreamOnlyGateway(),
            context=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            user_message="这个视频有哪些工具状态？",
            observed_tool_results=[],
            planner_transport=PLANNER_TRANSPORT_STREAM_BUFFERED,
        )

        self.assertEqual([call.tool_name.value for call in plan.tool_calls], ["get_video_tools"])

    def test_stream_buffered_transport_falls_back_to_non_stream_when_stream_is_empty(self) -> None:
        gateway = _EmptyStreamGateway()

        plan = generate_execution_plan(
            gateway=gateway,
            context=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            user_message="直接回复",
            observed_tool_results=[],
            planner_transport=PLANNER_TRANSPORT_STREAM_BUFFERED,
        )

        self.assertTrue(gateway.fallback_called)
        self.assertEqual(plan.direct_response, "ok")


if __name__ == "__main__":
    unittest.main()
