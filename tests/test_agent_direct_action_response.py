from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.agent.service import AgentService
from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext, ToolAvailability
from backend.agent.memory.store import InMemoryAgentMemoryStore
from backend.agent.runtime.request_router import REQUEST_ROUTER_SYSTEM_PROMPT
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName
from backend.agent.agent.execution import RegistryAgentToolExecutor


class _ActionGateway:
    def __init__(self) -> None:
        self.text_completion_calls = 0

    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion_stream(self, messages):
        del messages
        raise AssertionError("动作类请求不应进入 responder stream。")

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        self.text_completion_calls += 1
        if REQUEST_ROUTER_SYSTEM_PROMPT in messages[0].content:
            return '{"kind":"open_tool","tool_name":"open_overview","reason":"这是明确的打开概况请求。"}'
        raise AssertionError("动作类请求不应进入 responder completion。")


class AgentDirectActionResponseTests(unittest.TestCase):
    def test_open_tool_route_skips_responder_completion(self) -> None:
        gateway = _ActionGateway()

        def fake_open_overview(call, context):
            del call, context
            return ToolExecutionResult(
                tool_name=ToolName.OPEN_OVERVIEW,
                status="ok",
                payload={"selected_tool": "overview"},
            )

        service = AgentService(
            gateway=gateway,
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="video|series-a|video-1|overview",
                    scope_type="video",
                    series_id="series-a",
                    video_id="video-1",
                    overview=ToolAvailability(available=True, generated=True, status="ready"),
                )
            ),
            memory_store=InMemoryAgentMemoryStore(),
            tool_executor=RegistryAgentToolExecutor(
                registry={
                    ToolName.OPEN_OVERVIEW: fake_open_overview,
                }
            ),
        )

        result = service.run("video|series-a|video-1|overview", "打开概况")

        self.assertEqual(result.assistant_message, "我已经帮你打开概况工具。")
        self.assertEqual(gateway.text_completion_calls, 1)

    def test_open_overview_generates_when_overview_is_missing(self) -> None:
        gateway = _ActionGateway()
        executed_tool_names: list[ToolName] = []

        def fake_generate_overview(call, context):
            del call, context
            executed_tool_names.append(ToolName.GENERATE_OVERVIEW)
            return ToolExecutionResult(
                tool_name=ToolName.GENERATE_OVERVIEW,
                status="ok",
                payload={"action": "generate_overview", "selected_tool": "overview"},
            )

        def fake_open_overview(call, context):
            del call, context
            executed_tool_names.append(ToolName.OPEN_OVERVIEW)
            return ToolExecutionResult(
                tool_name=ToolName.OPEN_OVERVIEW,
                status="ok",
                payload={"selected_tool": "overview"},
            )

        service = AgentService(
            gateway=gateway,
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="video|series-a|video-1|overview",
                    scope_type="video",
                    series_id="series-a",
                    video_id="video-1",
                    overview=ToolAvailability(available=True, generated=False, status="idle"),
                )
            ),
            memory_store=InMemoryAgentMemoryStore(),
            tool_executor=RegistryAgentToolExecutor(
                registry={
                    ToolName.GENERATE_OVERVIEW: fake_generate_overview,
                    ToolName.OPEN_OVERVIEW: fake_open_overview,
                }
            ),
        )

        result = service.run("video|series-a|video-1|overview", "打开概况")

        self.assertEqual(executed_tool_names, [ToolName.GENERATE_OVERVIEW, ToolName.OPEN_OVERVIEW])
        self.assertEqual(result.assistant_message, "我已经开始帮你生成并打开概况工具。")
        self.assertEqual(gateway.text_completion_calls, 1)

    def test_open_mindmap_generates_when_mindmap_is_missing(self) -> None:
        class _MindmapGateway(_ActionGateway):
            def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
                self.text_completion_calls += 1
                if REQUEST_ROUTER_SYSTEM_PROMPT in messages[0].content:
                    return '{"kind":"open_tool","tool_name":"open_mindmap","reason":"这是明确的打开思维导图请求。"}'
                raise AssertionError("动作类请求不应进入 responder completion。")

        gateway = _MindmapGateway()
        executed_tool_names: list[ToolName] = []

        def fake_generate_mindmap(call, context):
            del call, context
            executed_tool_names.append(ToolName.GENERATE_MINDMAP)
            return ToolExecutionResult(
                tool_name=ToolName.GENERATE_MINDMAP,
                status="ok",
                payload={"action": "generate_mindmap", "selected_tool": "mindmap"},
            )

        def fake_open_mindmap(call, context):
            del call, context
            executed_tool_names.append(ToolName.OPEN_MINDMAP)
            return ToolExecutionResult(
                tool_name=ToolName.OPEN_MINDMAP,
                status="ok",
                payload={"selected_tool": "mindmap"},
            )

        service = AgentService(
            gateway=gateway,
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="video|series-a|video-1|mindmap",
                    scope_type="video",
                    series_id="series-a",
                    video_id="video-1",
                    mindmap=ToolAvailability(available=True, generated=False, status="idle"),
                )
            ),
            memory_store=InMemoryAgentMemoryStore(),
            tool_executor=RegistryAgentToolExecutor(
                registry={
                    ToolName.GENERATE_MINDMAP: fake_generate_mindmap,
                    ToolName.OPEN_MINDMAP: fake_open_mindmap,
                }
            ),
        )

        result = service.run("video|series-a|video-1|mindmap", "打开思维导图")

        self.assertEqual(executed_tool_names, [ToolName.GENERATE_MINDMAP, ToolName.OPEN_MINDMAP])
        self.assertEqual(result.assistant_message, "我已经开始帮你生成并打开思维导图。")
        self.assertEqual(gateway.text_completion_calls, 1)


if __name__ == "__main__":
    unittest.main()
