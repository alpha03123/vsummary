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
from backend.agent.agent.service import _apply_tool_result_to_context
from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext, InspectionStage, ToolAvailability
from backend.agent.memory.store import InMemoryAgentMemoryStore
from backend.agent.runtime.planner import INITIAL_PLANNER_SYSTEM_PROMPT
from backend.agent.runtime.routed_answerer import ROUTED_ANSWERER_SYSTEM_PROMPT
from backend.agent.schemas.action_plan import AgentActionPlan, ScopeType
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import GetVideoSummaryCall, ToolExecutionResult, ToolName
from backend.agent.session.store import FileAgentSessionStore
from backend.agent.tools import list_tool_definitions_for_context
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.plan import validate_action_plan


class FakeGateway:
    def create_structured_completion(self, messages: list[AgentChatMessage], response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        system_prompt = messages[0].content if messages else ""
        user_message = messages[-1].content if messages else ""

        if INITIAL_PLANNER_SYSTEM_PROMPT in system_prompt:
            payload = json.loads(user_message)
            observed = payload.get("observed_tool_results", [])
            context = payload.get("context", {})
            if any(item.get("tool_name") == "video_seek" for item in observed):
                return '{"scope_type":"video","tool_calls":[],"reason":"动作已完成。","direct_response":"这是最终回答","use_answerer":false}'
            if any(item.get("tool_name") == "open_overview" for item in observed):
                return '{"scope_type":"video","tool_calls":[],"reason":"动作已完成。","direct_response":"这是最终回答","use_answerer":false}'
            if any(item.get("tool_name") == "get_video_transcript" for item in observed):
                if "视频哪里" in payload.get("user_message", "") or "什么位置" in payload.get("user_message", ""):
                    return '{"scope_type":"video","tool_calls":[{"tool_name":"video_seek","seek_seconds":320}],"reason":"已经根据转写找到相关时间点。","direct_response":"","use_answerer":false}'
                return '{"scope_type":"video","tool_calls":[],"reason":"证据已足够。","direct_response":"","use_answerer":true}'
            if any(item.get("tool_name") == "get_video_summary" for item in observed):
                return '{"scope_type":"video","tool_calls":[],"reason":"证据已足够。","direct_response":"","use_answerer":true}'
            if any(item.get("tool_name") == "list_series_videos" for item in observed):
                videos = payload.get("observed_tool_results", [{}])[-1].get("payload", {}).get("videos", [])
                if len(videos) > 1:
                    return '{"scope_type":"series","tool_calls":[{"tool_name":"get_video_summary","video_id":"video-1"},{"tool_name":"get_video_summary","video_id":"video-2"}],"reason":"先批量读取已列出视频的概况。","direct_response":"","use_answerer":false}'
                return '{"scope_type":"series","tool_calls":[{"tool_name":"get_video_summary","video_id":"video-1"}],"reason":"先读取视频概况。","direct_response":"","use_answerer":false}'
            if context.get("scope_type") == "series":
                return '{"scope_type":"series","tool_calls":[{"tool_name":"list_series_videos","series_id":"series-a"}],"reason":"这是系列概括型问题。","direct_response":"","use_answerer":false}'
            if "原话" in payload.get("user_message", ""):
                return '{"scope_type":"video","tool_calls":[{"tool_name":"get_video_transcript","series_id":"series-a","video_id":"video-1"}],"reason":"这是原话型问题。","direct_response":"","use_answerer":false}'
            if "视频哪里" in payload.get("user_message", "") or "什么位置" in payload.get("user_message", ""):
                return '{"scope_type":"video","tool_calls":[{"tool_name":"video_seek","seek_seconds":320}],"reason":"已经根据转写找到相关时间点。","direct_response":"","use_answerer":false}'
            if "打开概况" in payload.get("user_message", ""):
                return '{"scope_type":"video","tool_calls":[{"tool_name":"open_overview"}],"reason":"这是明确的打开概况请求。","direct_response":"","use_answerer":false}'
            return '{"scope_type":"video","tool_calls":[{"tool_name":"get_video_summary","series_id":"series-a","video_id":"video-1"}],"reason":"这是概括型问题。","direct_response":"","use_answerer":false}'
        if ROUTED_ANSWERER_SYSTEM_PROMPT in system_prompt:
            return "这是最终回答"
        return "这是最终回答"

    def create_text_completion_stream(self, messages: list[AgentChatMessage]):
        yield self.create_text_completion(messages)


def fake_video_seek(call, context: AgentContext) -> ToolExecutionResult:
    del context
    return ToolExecutionResult(
        tool_name=ToolName.VIDEO_SEEK,
        status="ok",
        payload={
            "seek_seconds": call.seek_seconds,
        },
    )


def fake_video_summary(call, context: AgentContext) -> ToolExecutionResult:
    del context
    return ToolExecutionResult(
        tool_name=ToolName.GET_VIDEO_SUMMARY,
        status="ok",
        payload={"video_id": call.video_id or ""},
    )


class AgentScaffoldTests(unittest.TestCase):
    def test_tool_visibility_is_split_by_stage(self) -> None:
        series_discovery_tools = {
            tool.name.value
            for tool in list_tool_definitions_for_context(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                    inspection_stage=InspectionStage.SERIES_DISCOVERY,
                )
            )
        }
        video_inspection_tools = {
            tool.name.value
            for tool in list_tool_definitions_for_context(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                    inspection_stage=InspectionStage.VIDEO_INSPECTION,
                )
            )
        }

        self.assertIn("list_series_videos", series_discovery_tools)
        self.assertNotIn("get_video_summary", series_discovery_tools)
        self.assertIn("get_video_summary", video_inspection_tools)
        self.assertIn("get_video_transcript", video_inspection_tools)

    def test_agent_service_executes_video_seek_route_without_planner(self) -> None:
        gateway = FakeGateway()

        def fake_get_video_transcript(call, context):
            del context
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                status="ok",
                payload={"video_id": call.video_id, "generated": True, "segments": []},
            )

        service = AgentService(
            gateway=gateway,
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="session-1",
                    scope_type="video",
                    series_id="series-a",
                    video_id="video-1",
                )
            ),
            memory_store=InMemoryAgentMemoryStore(),
            tool_executor=RegistryAgentToolExecutor(
                registry={
                    ToolName.GET_VIDEO_TRANSCRIPT: fake_get_video_transcript,
                    ToolName.VIDEO_SEEK: fake_video_seek,
                }
            ),
        )

        result = service.run("session-1", "这个内容在视频哪里？")

        self.assertEqual(result.tool_results[-1].payload["seek_seconds"], 320)
        self.assertEqual(result.assistant_message, "这是最终回答")

    def test_video_answer_question_uses_initial_summary_evidence_plan(self) -> None:
        gateway = FakeGateway()
        executed_calls: list[str] = []

        def fake_get_video_summary(call, context):
            del context
            executed_calls.append(f"get_video_summary:{call.video_id}")
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={"video_id": call.video_id, "generated": True, "title": "Video 1"},
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
                registry={
                    ToolName.GET_VIDEO_SUMMARY: fake_get_video_summary,
                }
            ),
        )

        result = service.run("video|series-a|video-1|overview", "这个视频主要讲了什么？")

        self.assertEqual(executed_calls, ["get_video_summary:video-1"])

    def test_video_quote_question_uses_initial_transcript_evidence_plan(self) -> None:
        gateway = FakeGateway()
        executed_calls: list[str] = []

        def fake_get_video_transcript(call, context):
            del context
            executed_calls.append(f"get_video_transcript:{call.video_id}")
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                status="ok",
                payload={"video_id": call.video_id, "generated": True, "segments": []},
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
                registry={
                    ToolName.GET_VIDEO_TRANSCRIPT: fake_get_video_transcript,
                }
            ),
        )

        result = service.run("video|series-a|video-1|overview", "视频原话里是怎么说的？")

        self.assertEqual(executed_calls, ["get_video_transcript:video-1"])

    def test_video_tool_status_question_reads_structured_tool_status(self) -> None:
        gateway = FakeGateway()
        executed_calls: list[str] = []

        def fake_get_video_tools(call, context):
            del context
            executed_calls.append(f"get_video_tools:{call.video_id}")
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_TOOLS,
                status="ok",
                payload={
                    "video_id": call.video_id,
                    "overview": {"available": True, "generated": True, "status": "ready"},
                    "mindmap": {"available": True, "generated": True, "status": "ready"},
                    "knowledge_cards": {"available": True, "generated": False, "status": "available"},
                    "notes": {"available": True, "generated": True, "status": "ready"},
                    "preview": {"available": True, "generated": True, "status": "ready"},
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
                    overview=ToolAvailability(available=True, generated=True, status="ready"),
                    mindmap=ToolAvailability(available=True, generated=True, status="ready"),
                    knowledge_cards=ToolAvailability(available=True, generated=False, status="available"),
                    notes=ToolAvailability(available=True, generated=True, status="ready"),
                    preview=ToolAvailability(available=True, generated=True, status="ready"),
                )
            ),
            memory_store=InMemoryAgentMemoryStore(),
            tool_executor=RegistryAgentToolExecutor(
                registry={
                    ToolName.GET_VIDEO_TOOLS: fake_get_video_tools,
                }
            ),
        )

        service.run("video|series-a|video-1|overview", "这个视频现在有哪些工具已经生成了？导图、知识卡片、笔记分别是什么状态？")

        self.assertEqual(executed_calls, ["get_video_tools:video-1"])

    def test_video_scope_boundary_question_guides_user_to_series_scope(self) -> None:
        gateway = FakeGateway()

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
            tool_executor=RegistryAgentToolExecutor(registry={}),
        )

        result = service.run("video|series-a|video-1|overview", "当前这个视频讲的是 API Key，那后面哪一节最可能与它衔接？")

        self.assertIn("系列", result.assistant_message)

    def test_executor_allows_video_read_tool_when_inspection_buffer_is_empty(self) -> None:
        executor = RegistryAgentToolExecutor(
            registry={
                ToolName.GET_VIDEO_SUMMARY: fake_video_summary,
            }
        )
        context = AgentContext(
            session_id="series|series-a|series-home",
            scope_type="series",
            series_id="series-a",
            inspection_stage=InspectionStage.VIDEO_INSPECTION,
        )

        result = executor.execute_call(
            GetVideoSummaryCall(tool_name="get_video_summary", video_id="video-1"),
            context,
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.payload["video_id"], "video-1")

    def test_apply_tool_result_updates_selected_tool_from_payload(self) -> None:
        context = AgentContext(
            session_id="video|series-a|video-1|studio",
            scope_type="video",
            series_id="series-a",
            video_id="video-1",
            selected_tool="studio",
        )

        next_context = _apply_tool_result_to_context(
            context,
            ToolExecutionResult(
                tool_name=ToolName.OPEN_KNOWLEDGE_CARDS,
                status="ok",
                payload={"selected_tool": "knowledge-cards"},
            ),
        )

        self.assertEqual(next_context.selected_tool, "knowledge-cards")

    def test_series_answer_uses_initial_series_evidence_plan(self) -> None:
        gateway = FakeGateway()
        executed_calls: list[str] = []

        def fake_list_series_videos(call, context):
            del context
            executed_calls.append(f"list_series_videos:{call.series_id}")
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={
                    "series_id": call.series_id,
                    "videos": [{"video_id": "video-1", "title": "Video 1", "processed": True, "status": "ready"}],
                },
            )

        def fake_get_video_summary(call, context):
            del context
            executed_calls.append(f"get_video_summary:{call.video_id}")
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

        result = service.run("series|series-a|series-home", "这个系列主要讲了哪些主题？")

        self.assertEqual(executed_calls, ["list_series_videos:series-a", "get_video_summary:video-1"])

    def test_executor_guard_blocks_deep_tools_before_candidate_selection(self) -> None:
        executor = RegistryAgentToolExecutor(registry={})
        with self.assertRaises(AgentPlanError):
            executor.execute_call(
                AgentActionPlan.model_validate(
                    {
                        "scope_type": "series",
                        "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-1"}],
                        "reason": "错误读取",
                        "direct_response": "",
                        "use_answerer": False,
                    }
                ).tool_calls[0],
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                    inspection_stage=InspectionStage.SERIES_DISCOVERY,
                ),
            )

    def test_validate_action_plan_rejects_missing_seek_seconds(self) -> None:
        with self.assertRaises(Exception):
            validate_action_plan(
                AgentActionPlan.model_validate(
                    {
                        "use_answerer": True,
                        "scope_type": ScopeType.VIDEO,
                        "tool_calls": [{"tool_name": "video_seek"}],
                        "reason": "",
                        "direct_response": "",
                    }
                ),
                AgentContext(
                    session_id="video|series-a|video-1|studio",
                    scope_type="video",
                    series_id="series-a",
                    video_id="video-1",
                ),
            )

    def test_updated_context_is_persisted_into_session_snapshot(self) -> None:
        def fake_list_series_videos(call, context):
            del call, context
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "series_title": "Series A",
                    "videos": [{"video_id": "video-1", "title": "Video 1", "processed": True, "status": "ready"}],
                },
            )

        def fake_get_video_summary(call, context):
            del context
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={"video_id": call.video_id, "generated": True, "title": "Video 1"},
            )

        temp_root = ROOT / "temp" / "agent-scaffold-sessions"
        if temp_root.exists():
            for file in temp_root.glob("*.json"):
                file.unlink()
        store = FileAgentSessionStore(temp_root)
        service = AgentService(
            gateway=FakeGateway(),
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
        snapshot = store.get_snapshot("series|series-a|series-home")

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.context.inspection_stage, InspectionStage.ANSWER_READY)


if __name__ == "__main__":
    unittest.main()
