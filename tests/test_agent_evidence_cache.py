from __future__ import annotations

import tempfile
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
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName
from backend.agent.session.store import FileAgentSessionStore


class _CacheGateway:
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
        raise AssertionError("该用例只验证非流式路径。")

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        system_prompt = messages[0].content
        if REQUEST_ROUTER_SYSTEM_PROMPT in system_prompt:
            self.router_calls += 1
            return self._route_payload
        if ROUTED_ANSWERER_SYSTEM_PROMPT in system_prompt:
            self.answerer_calls += 1
            return self._answer_text
        raise AssertionError("缓存用例不应进入其他模型路径。")


class AgentEvidenceCacheTests(unittest.TestCase):
    def test_video_summary_reuses_cached_summary_on_second_turn(self) -> None:
        gateway = _CacheGateway(
            route_payload='{"kind":"video_summary","tool_name":null,"reason":"这是视频概括型问题。"}',
            answer_text="这是视频概括。",
        )
        summary_calls = 0

        def fake_get_video_summary(call, context):
            nonlocal summary_calls
            del context
            summary_calls += 1
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "video_id": call.video_id,
                    "generated": True,
                    "title": "Video 1",
                    "one_sentence_summary": "summary",
                },
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileAgentSessionStore(Path(temp_dir))
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
                session_store=store,
                tool_executor=RegistryAgentToolExecutor(
                    registry={ToolName.GET_VIDEO_SUMMARY: fake_get_video_summary}
                ),
            )

            service.run("video|series-a|video-1|overview", "这个视频主要讲了什么？")
            service.run("video|series-a|video-1|overview", "再说一遍这个视频主要讲了什么？")

            self.assertEqual(summary_calls, 1)
            snapshot = store.get_snapshot("video|series-a|video-1|overview")
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertEqual(len(snapshot.evidence_entries), 1)
            self.assertEqual(snapshot.evidence_entries[0].tool_result.tool_name, ToolName.GET_VIDEO_SUMMARY)

    def test_series_summary_reuses_cached_list_and_summaries_on_second_turn(self) -> None:
        gateway = _CacheGateway(
            route_payload='{"kind":"series_summary","tool_name":null,"reason":"这是系列概括型问题。"}',
            answer_text="这是系列概括。",
        )
        list_calls = 0
        summary_calls = 0

        def fake_list_series_videos(call, context):
            nonlocal list_calls
            del call, context
            list_calls += 1
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "videos": [
                        {"video_id": "video-1", "title": "Video 1", "processed": True, "status": "ready"},
                        {"video_id": "video-2", "title": "Video 2", "processed": True, "status": "ready"},
                    ],
                },
            )

        def fake_get_video_summary(call, context):
            nonlocal summary_calls
            del context
            summary_calls += 1
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "video_id": call.video_id,
                    "generated": True,
                    "title": call.video_id,
                    "one_sentence_summary": "summary",
                },
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileAgentSessionStore(Path(temp_dir))
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
                session_store=store,
                tool_executor=RegistryAgentToolExecutor(
                    registry={
                        ToolName.LIST_SERIES_VIDEOS: fake_list_series_videos,
                        ToolName.GET_VIDEO_SUMMARY: fake_get_video_summary,
                    }
                ),
            )

            service.run("series|series-a|series-home", "这个系列主要讲了哪些主题？")
            service.run("series|series-a|series-home", "再总结一下这个系列主要讲了哪些主题？")

            self.assertEqual(list_calls, 1)
            self.assertEqual(summary_calls, 2)
            snapshot = store.get_snapshot("series|series-a|series-home")
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            cached_tool_names = {entry.tool_result.tool_name for entry in snapshot.evidence_entries}
            self.assertEqual(
                cached_tool_names,
                {ToolName.LIST_SERIES_VIDEOS, ToolName.GET_VIDEO_SUMMARY},
            )


if __name__ == "__main__":
    unittest.main()
