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
from backend.agent.runtime.planner import INITIAL_PLANNER_SYSTEM_PROMPT
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class _SaveNoteGateway:
    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion_stream(self, messages):
        del messages
        raise AssertionError("保存笔记主路径不应进入流式回答器。")

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        if INITIAL_PLANNER_SYSTEM_PROMPT in messages[0].content:
            observed = messages[-1].content
            if '"tool_name": "save_note"' in observed:
                return '{"scope_type":"video","tool_calls":[],"reason":"笔记已保存。","direct_response":"我已经帮你记好这条笔记。","use_answerer":false}'
            if '"tool_name": "get_video_summary"' in observed:
                return (
                    '{"scope_type":"video","tool_calls":[{"tool_name":"save_note",'
                    '"note_title":"百度地图 AK 准备重点",'
                    '"note_content":"- 先准备百度地图 AK\\n- 这是后续能力接入的前置条件"}],'
                    '"reason":"概况已经足够支撑整理重点。","direct_response":"","use_answerer":false}'
                )
            return '{"scope_type":"video","tool_calls":[{"tool_name":"get_video_summary","series_id":"series-a","video_id":"video-1"}],"reason":"这是明确的记笔记请求。","direct_response":"","use_answerer":false}'
        raise AssertionError("保存笔记主路径不应退回旧 planner 或旧 responder。")


class AgentSaveNoteRouteTests(unittest.TestCase):
    def test_save_note_request_uses_routed_note_workflow(self) -> None:
        gateway = _SaveNoteGateway()

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
                    "key_takeaways": ["需要先准备百度地图 AK"],
                },
            )

        def fake_save_note(call, context):
            del context
            return ToolExecutionResult(
                tool_name=ToolName.SAVE_NOTE,
                status="ok",
                payload={
                    "action": "save_note",
                    "selected_tool": "notes",
                    "note_title": call.note_title,
                    "note_content": call.note_content,
                    "note_source": "agent",
                },
            )

        service = AgentService(
            gateway=gateway,
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="video|series-a|video-1|studio",
                    scope_type="video",
                    series_id="series-a",
                    video_id="video-1",
                )
            ),
            memory_store=InMemoryAgentMemoryStore(),
            tool_executor=RegistryAgentToolExecutor(
                registry={
                    ToolName.GET_VIDEO_SUMMARY: fake_get_video_summary,
                    ToolName.SAVE_NOTE: fake_save_note,
                }
            ),
        )

        result = service.run("video|series-a|video-1|studio", "帮我记一下这个视频的重点")

        self.assertEqual(
            [item.tool_name for item in result.tool_results],
            [ToolName.GET_VIDEO_SUMMARY, ToolName.SAVE_NOTE],
        )
        self.assertEqual(result.tool_results[-1].payload["note_title"], "百度地图 AK 准备重点")
        self.assertIn("百度地图 AK", result.tool_results[-1].payload["note_content"])
        self.assertEqual(result.assistant_message, "我已经帮你记好这条笔记。")


if __name__ == "__main__":
    unittest.main()
