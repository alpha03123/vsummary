from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.agent.service import AgentService
from backend.agent.agent.execution import RegistryAgentToolExecutor
from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import InMemoryAgentMemoryStore
from backend.agent.runtime.planner import INITIAL_PLANNER_SYSTEM_PROMPT
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class _BatchGateway:
    def _is_request_router_call(self, messages: list[AgentChatMessage]) -> bool:
        return bool(messages) and INITIAL_PLANNER_SYSTEM_PROMPT in messages[0].content

    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        if self._is_request_router_call(messages):
            payload = json.loads(messages[-1].content)
            observed = payload.get("observed_tool_results", [])
            if any(item.get("tool_name") == "get_video_summary" for item in observed):
                return '{"scope_type":"series","tool_calls":[],"reason":"已有足够证据。","direct_response":"done","use_answerer":false}'
            if any(item.get("tool_name") == "list_series_videos" for item in observed):
                return '{"scope_type":"series","tool_calls":[{"tool_name":"get_video_summary","video_id":"video-1"},{"tool_name":"get_video_summary","video_id":"video-2"}],"reason":"已拿到视频列表，继续并发读取概况。","direct_response":"","use_answerer":false}'
            return '{"scope_type":"series","tool_calls":[{"tool_name":"list_series_videos","series_id":"series-a"}],"reason":"这是系列概括型问题。","direct_response":"","use_answerer":false}'
        return "done"

    def create_text_completion_stream(self, messages):
        del messages
        yield "done"


class AgentRuntimeBatchingTests(unittest.TestCase):
    def test_concurrency_safe_batch_executes_overlapping_reads(self) -> None:
        gateway = _BatchGateway()
        lock = threading.Lock()
        current_concurrency = 0
        max_concurrency = 0

        def fake_list_series_videos(call, context):
            del call, context
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={
                    "videos": [
                        {"video_id": "video-1", "title": "Video 1"},
                        {"video_id": "video-2", "title": "Video 2"},
                    ]
                },
            )

        def fake_summary(call, context):
            nonlocal current_concurrency, max_concurrency
            del context
            with lock:
                current_concurrency += 1
                max_concurrency = max(max_concurrency, current_concurrency)
            time.sleep(0.12)
            with lock:
                current_concurrency -= 1
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={"video_id": call.video_id},
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
                    ToolName.GET_VIDEO_SUMMARY: fake_summary,
                }
            ),
        )

        started_at = time.perf_counter()
        result = service.run("series|series-a|series-home", "这个系列主要讲了哪些主题？")
        duration = time.perf_counter() - started_at

        self.assertEqual(
            [
                item.payload["video_id"]
                for item in result.tool_results
                if item.tool_name == ToolName.GET_VIDEO_SUMMARY
            ],
            ["video-1", "video-2"],
        )
        self.assertGreaterEqual(max_concurrency, 2)
        self.assertLess(duration, 0.22)


if __name__ == "__main__":
    unittest.main()
