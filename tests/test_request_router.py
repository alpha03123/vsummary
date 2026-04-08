from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext
from backend.agent.runtime.request_router import (
    REQUEST_ROUTER_SYSTEM_PROMPT,
    RouteKind,
    RouteToolName,
    classify_initial_route,
)
from backend.agent.schemas.messages import AgentChatMessage


class _RouterGateway:
    def __init__(self, response: str) -> None:
        self._response = response

    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion_stream(self, messages):
        del messages
        yield ""

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        assert REQUEST_ROUTER_SYSTEM_PROMPT in messages[0].content
        return self._response


class RequestRouterTests(unittest.TestCase):
    def test_series_summary_request_routes_to_series_summary(self) -> None:
        decision = classify_initial_route(
            gateway=_RouterGateway('{"kind":"series_summary","tool_name":null,"reason":"这是系列概括型问题。"}'),
            context=AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
            ),
            user_message="这个系列主要讲了哪些主题？",
        )

        self.assertEqual(decision.kind, RouteKind.SERIES_SUMMARY)

    def test_series_locate_request_routes_to_series_locate(self) -> None:
        decision = classify_initial_route(
            gateway=_RouterGateway('{"kind":"series_locate","tool_name":null,"reason":"这是系列定位问题。"}'),
            context=AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
            ),
            user_message="这个系列里哪里讲过 Nacos 3？",
        )

        self.assertEqual(decision.kind, RouteKind.SERIES_LOCATE)

    def test_video_quote_request_routes_to_video_transcript(self) -> None:
        decision = classify_initial_route(
            gateway=_RouterGateway('{"kind":"video_transcript","tool_name":null,"reason":"这是原话型问题。"}'),
            context=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            user_message="视频原话里是怎么说的？",
        )

        self.assertEqual(decision.kind, RouteKind.VIDEO_TRANSCRIPT)

    def test_open_request_routes_to_open_tool(self) -> None:
        decision = classify_initial_route(
            gateway=_RouterGateway('{"kind":"open_tool","tool_name":"open_overview","reason":"这是明确的打开概况请求。"}'),
            context=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            user_message="打开概况",
        )

        self.assertEqual(decision.kind, RouteKind.OPEN_TOOL)
        self.assertEqual(decision.tool_name, RouteToolName.OPEN_OVERVIEW)

    def test_note_request_routes_to_save_note(self) -> None:
        decision = classify_initial_route(
            gateway=_RouterGateway('{"kind":"save_note","tool_name":null,"reason":"这是明确的记笔记请求。"}'),
            context=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            user_message="帮我记一下这个视频的重点",
        )

        self.assertEqual(decision.kind, RouteKind.SAVE_NOTE)

    def test_out_of_scope_request_routes_to_out_of_scope(self) -> None:
        decision = classify_initial_route(
            gateway=_RouterGateway('{"kind":"out_of_scope","tool_name":null,"reason":"这是明显超范围请求。"}'),
            context=AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
            ),
            user_message="帮我写一份旅游攻略",
        )

        self.assertEqual(decision.kind, RouteKind.OUT_OF_SCOPE)


if __name__ == "__main__":
    unittest.main()
