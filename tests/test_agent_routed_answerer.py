from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.agent.execution import RegistryAgentToolExecutor
from backend.agent.agent.service import AgentService
from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import InMemoryAgentMemoryStore
from backend.agent.runtime.planner import INITIAL_PLANNER_SYSTEM_PROMPT
from backend.agent.runtime.routed_answerer import ROUTED_ANSWERER_SYSTEM_PROMPT
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class _RoutedAnswerGateway:
    def __init__(self, route_payload: str, answer_text: str) -> None:
        self._route_payload = route_payload
        self._answer_text = answer_text
        self.router_calls = 0
        self.answerer_calls = 0

    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion_stream(self, messages):
        del messages
        raise AssertionError("该用例只验证非流式 routed answer。")

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        system_prompt = messages[0].content
        if INITIAL_PLANNER_SYSTEM_PROMPT in system_prompt:
            self.router_calls += 1
            payload = json.loads(messages[-1].content)
            observed = payload.get("observed_tool_results", [])
            if any(item.get("tool_name") == "get_video_summary" for item in observed):
                return '{"scope_type":"video","tool_calls":[],"reason":"证据已足够。","direct_response":"","use_answerer":true}'
            if any(item.get("tool_name") == "list_series_videos" for item in observed):
                return '{"scope_type":"series","tool_calls":[{"tool_name":"get_video_summary","video_id":"video-1"},{"tool_name":"get_video_summary","video_id":"video-2"}],"reason":"先批量读取系列概况。","direct_response":"","use_answerer":false}'
            return self._route_payload
        if ROUTED_ANSWERER_SYSTEM_PROMPT in system_prompt:
            self.answerer_calls += 1
            return self._answer_text
        raise AssertionError("新的 routed QA 主路径不应回退到旧 planner / responder。")


class AgentRoutedAnswererTests(unittest.TestCase):
    def test_video_summary_route_uses_lightweight_answerer(self) -> None:
        gateway = _RoutedAnswerGateway(
            route_payload='{"scope_type":"video","tool_calls":[{"tool_name":"get_video_summary","series_id":"series-a","video_id":"video-1"}],"reason":"这是视频概括型问题。","direct_response":"","use_answerer":false}',
            answer_text="这个视频主要在讲百度地图 AK 的准备步骤，以及它为什么是后续能力接入的前置条件。",
        )

        def fake_get_video_summary(call, context):
            del context
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={
                    "video_id": call.video_id,
                    "generated": True,
                    "title": "百度地图 API Key",
                    "one_sentence_summary": "介绍准备百度地图 AK 的前置步骤。",
                    "key_takeaways": ["准备百度地图 AK", "用于后续能力接入"],
                },
            )

        service = AgentService(
            gateway=gateway,
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="video|series-a|video-1|overview",
                    scope_type="video",
                    series_id="series-a",
                    video_id="video-1",
                )
            ),
            memory_store=InMemoryAgentMemoryStore(),
            tool_executor=RegistryAgentToolExecutor(
                registry={ToolName.GET_VIDEO_SUMMARY: fake_get_video_summary}
            ),
        )

        result = service.run("video|series-a|video-1|overview", "这个视频主要讲了什么？")

        self.assertEqual(result.assistant_message, gateway._answer_text)
        self.assertEqual(gateway.router_calls, 2)
        self.assertEqual(gateway.answerer_calls, 1)

    def test_series_summary_route_uses_lightweight_answerer_after_batch_reads(self) -> None:
        gateway = _RoutedAnswerGateway(
            route_payload='{"scope_type":"series","tool_calls":[{"tool_name":"list_series_videos","series_id":"series-a"}],"reason":"这是系列概括型问题。","direct_response":"","use_answerer":false}',
            answer_text="这个系列先讲准备工作，再进入不同 Agent 框架的定位与能力差异。",
        )

        def fake_list_series_videos(call, context):
            del call, context
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={
                    "videos": [
                        {"video_id": "video-1", "title": "准备工作", "processed": True, "status": "ready"},
                        {"video_id": "video-2", "title": "框架介绍", "processed": True, "status": "ready"},
                    ]
                },
            )

        def fake_get_video_summary(call, context):
            del context
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={
                    "video_id": call.video_id,
                    "generated": True,
                    "title": call.video_id,
                    "one_sentence_summary": f"{call.video_id} 的概括",
                    "key_takeaways": [f"{call.video_id} 的重点"],
                },
            )

        service = AgentService(
            gateway=gateway,
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                )
            ),
            memory_store=InMemoryAgentMemoryStore(),
            tool_executor=RegistryAgentToolExecutor(
                registry={
                    ToolName.LIST_SERIES_VIDEOS: fake_list_series_videos,
                    ToolName.GET_VIDEO_SUMMARY: fake_get_video_summary,
                }
            ),
        )

        result = service.run("series|series-a|series-home", "这个系列主要讲了哪些主题？")

        self.assertEqual(result.assistant_message, gateway._answer_text)
        self.assertEqual(
            [item.tool_name for item in result.tool_results],
            [ToolName.LIST_SERIES_VIDEOS, ToolName.GET_VIDEO_SUMMARY, ToolName.GET_VIDEO_SUMMARY],
        )
        self.assertEqual(gateway.router_calls, 3)
        self.assertEqual(gateway.answerer_calls, 1)


if __name__ == "__main__":
    unittest.main()
