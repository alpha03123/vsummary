from __future__ import annotations

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
from backend.agent.runtime.request_router import REQUEST_ROUTER_SYSTEM_PROMPT
from backend.agent.runtime.routed_answerer import ROUTED_ANSWERER_SYSTEM_PROMPT
from backend.agent.runtime.series_locator import SERIES_LOCATOR_SYSTEM_PROMPT
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class _SeriesLocateGateway:
    def __init__(self) -> None:
        self.router_calls = 0
        self.selector_calls = 0
        self.answerer_calls = 0

    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion_stream(self, messages):
        del messages
        raise AssertionError("该用例只验证非流式 service 路径。")

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        system_prompt = messages[0].content
        if REQUEST_ROUTER_SYSTEM_PROMPT in system_prompt:
            self.router_calls += 1
            return '{"kind":"series_locate","tool_name":null,"reason":"这是系列定位类问题。"}'
        if SERIES_LOCATOR_SYSTEM_PROMPT in system_prompt:
            self.selector_calls += 1
            return '{"video_ids":["video-2"],"reason":"video-2 的 summary 明确提到了 Nacos 3。"}'
        if ROUTED_ANSWERER_SYSTEM_PROMPT in system_prompt:
            self.answerer_calls += 1
            return "在这个系列里，`Nacos 3` 主要出现在《1-5 准备工作：安装Nacos 3》中；从 transcript 看，相关说明集中在开头几分钟。"
        raise AssertionError("series locate routed path 不应退回旧 planner / responder。")


class AgentSeriesLocateRouteTests(unittest.TestCase):
    def test_series_locate_request_uses_summary_then_transcript(self) -> None:
        gateway = _SeriesLocateGateway()

        def fake_list_series_videos(call, context):
            del call, context
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={
                    "videos": [
                        {"video_id": "video-1", "title": "百度地图 API", "processed": True, "status": "ready"},
                        {"video_id": "video-2", "title": "安装 Nacos 3", "processed": True, "status": "ready"},
                    ]
                },
            )

        def fake_get_video_summary(call, context):
            del context
            title = "安装 Nacos 3" if call.video_id == "video-2" else "百度地图 API"
            takeaways = ["介绍 Nacos 3 安装与作用"] if call.video_id == "video-2" else ["介绍百度地图 AK"]
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={
                    "video_id": call.video_id,
                    "title": title,
                    "generated": True,
                    "key_takeaways": takeaways,
                },
            )

        def fake_get_video_transcript(call, context):
            del context
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                status="ok",
                payload={
                    "video_id": call.video_id,
                    "title": "安装 Nacos 3",
                    "generated": True,
                    "segments": [
                        {"start_seconds": 30, "end_seconds": 52, "text": "这里开始解释为什么课程使用 Nacos 3。"},
                    ],
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
                    ToolName.GET_VIDEO_TRANSCRIPT: fake_get_video_transcript,
                }
            ),
        )

        result = service.run("series|series-a|series-home", "这个系列里哪里讲过 Nacos 3？")

        self.assertEqual(result.plan.intent_type.value, "series_locate")
        self.assertEqual(
            [item.tool_name for item in result.tool_results],
            [ToolName.LIST_SERIES_VIDEOS, ToolName.GET_VIDEO_SUMMARY, ToolName.GET_VIDEO_SUMMARY, ToolName.GET_VIDEO_TRANSCRIPT],
        )
        self.assertEqual(gateway.router_calls, 1)
        self.assertEqual(gateway.selector_calls, 1)
        self.assertEqual(gateway.answerer_calls, 1)
        self.assertIn("Nacos 3", result.assistant_message)


if __name__ == "__main__":
    unittest.main()
