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
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class _StreamGateway:
    def __init__(self) -> None:
        self.router_calls = 0

    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        if REQUEST_ROUTER_SYSTEM_PROMPT in messages[0].content:
            self.router_calls += 1
            return '{"kind":"series_summary","tool_name":null,"reason":"这是系列概括型问题。"}'
        return "done"

    def create_text_completion_stream(self, messages):
        yield "done"


class AgentStreamBehaviorTests(unittest.TestCase):
    def test_deterministic_followup_does_not_emit_second_thinking_round(self) -> None:
        gateway = _StreamGateway()

        def fake_list_series_videos(call, context):
            del call, context
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={"videos": [{"video_id": "video-1", "title": "Video 1", "processed": True, "status": "ready"}]},
            )

        def fake_get_video_summary(call, context):
            del context
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={"video_id": call.video_id, "generated": True, "title": "Video 1"},
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

        event_types = [
            event.type
            for event in service.stream_with_context(
                session_id="series|series-a|series-home",
                user_message="Jmanus 和 AgentScope 在这个系列里分别承担什么角色？",
                context_override=None,
            )
        ]

        self.assertEqual(event_types.count("thinking_started"), 1)
        self.assertEqual(event_types.count("thinking_completed"), 1)
        self.assertEqual(gateway.router_calls, 1)


if __name__ == "__main__":
    unittest.main()
