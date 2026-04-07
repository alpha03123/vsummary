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
from backend.agent.agent.planner import _convert_planner_plan, extract_action_plan
from backend.agent.agent.prompt import PLANNER_SENTINEL
from backend.agent.agent.responder import _build_responder_input_view
from backend.agent.agent.service import AgentService
from backend.agent.agent.service import _apply_tool_result_to_context
from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext, CandidateBufferEntry, InspectionStage
from backend.agent.memory.store import InMemoryAgentMemoryStore
from backend.agent.schemas.action_plan import AgentActionPlan, IntentType, PlannerActionPlan, ScopeType
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import GetVideoSummaryCall, ToolExecutionResult, ToolName
from backend.agent.session.store import FileAgentSessionStore
from backend.agent.tools import list_tool_definitions_for_context
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.plan import validate_action_plan


class FakeGateway:
    def __init__(self) -> None:
        self.structured_calls: list[list[AgentChatMessage]] = []
        self.response_models: list[type] = []

    def _is_planner_call(self, messages: list[AgentChatMessage]) -> bool:
        return bool(messages) and "Planner Agent" in messages[0].content

    def build_planner_completion_from_plan(self, thinking: str, plan: dict[str, object]) -> str:
        return f"{thinking}\n{PLANNER_SENTINEL}\n{json.dumps(plan, ensure_ascii=False)}"

    def create_structured_completion(self, messages: list[AgentChatMessage], response_model):
        self.structured_calls.append(messages)
        self.response_models.append(response_model)
        raise NotImplementedError

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        if self._is_planner_call(messages):
            self.structured_calls.append(messages)
            self.response_models.append(PlannerActionPlan)
            user_message = messages[-1].content
            if '"tool_name": "video_seek"' in user_message:
                return self.build_planner_completion_from_plan(
                    "已经拿到定位结果，可以直接回答",
                    {
                        "intent_type": "answer_question",
                        "scope_type": "video",
                        "assistant_message": "",
                        "tool_calls": [],
                        "reason": "已经拿到定位结果，可以直接回答",
                        "out_of_scope_reason": "",
                    },
                )
            return self.build_planner_completion_from_plan(
                "先定位时间点",
                {
                    "intent_type": "seek_video",
                    "scope_type": "video",
                    "assistant_message": "",
                    "tool_calls": [{"tool_name": "video_seek", "seek_seconds": 320}],
                    "reason": "先定位时间点",
                    "out_of_scope_reason": "",
                },
            )
        return "## 定位结果\n\n这个内容大约在 05:20，可以直接看视频。"

    def create_text_completion_stream(self, messages: list[AgentChatMessage]):
        if self._is_planner_call(messages):
            self.structured_calls.append(messages)
            self.response_models.append(PlannerActionPlan)
            completion = self.create_text_completion(messages)
            midpoint = max(1, completion.find(PLANNER_SENTINEL))
            yield completion[:midpoint]
            yield completion[midpoint:]
            return
        yield "## 定位结果\n\n"
        yield "这个内容大约在 05:20，可以直接看视频。"


def fake_video_seek(call, context: AgentContext) -> ToolExecutionResult:
    del context
    return ToolExecutionResult(
        tool_name=ToolName.VIDEO_SEEK,
        status="ok",
        payload={
            "selected_tool": "video",
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
    def test_extract_action_plan_uses_planner_friendly_schema(self) -> None:
        gateway = FakeGateway()
        context = AgentContext(
            session_id="video|series-a|video-1|studio",
            scope_type="video",
            series_id="series-a",
            video_id="video-1",
        )

        plan = extract_action_plan(
            gateway=gateway,
            context=context,
            memory_store=InMemoryAgentMemoryStore(),
            session_id=context.session_id,
            user_message="这个内容在视频哪里？",
        )

        self.assertEqual(gateway.response_models[-1], PlannerActionPlan)
        self.assertEqual(plan.tool_calls[0].tool_name, ToolName.VIDEO_SEEK)

    def test_planner_action_plan_schema_avoids_one_of(self) -> None:
        self.assertNotIn("oneOf", str(PlannerActionPlan.model_json_schema()))

    def test_convert_planner_plan_maps_series_buffer_tools(self) -> None:
        planner_plan = PlannerActionPlan.model_validate(
            {
                "intent_type": "series_answer",
                "scope_type": "series",
                "tool_calls": [
                    {"tool_name": "list_series_videos", "series_id": "series-a"},
                    {"tool_name": "add_series_candidates", "video_ids": ["video-1"], "reason": "加入候选"},
                ],
                "reason": "先列列表，再建立候选",
            }
        )

        runtime_plan = _convert_planner_plan(planner_plan, planner_plan.reason)

        self.assertEqual(runtime_plan.tool_calls[0].tool_name, ToolName.LIST_SERIES_VIDEOS)
        self.assertEqual(runtime_plan.tool_calls[1].tool_name, ToolName.ADD_SERIES_CANDIDATES)

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
                    candidate_buffer=[CandidateBufferEntry(video_id="video-1", title="Video 1")],
                )
            )
        }

        self.assertIn("add_series_candidates", series_discovery_tools)
        self.assertNotIn("get_video_summary", series_discovery_tools)
        self.assertIn("get_video_summary", video_inspection_tools)
        self.assertIn("get_video_transcript", video_inspection_tools)

    def test_agent_service_executes_video_tool_calls(self) -> None:
        gateway = FakeGateway()
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
                    ToolName.VIDEO_SEEK: fake_video_seek,
                }
            ),
        )

        result = service.run("session-1", "这个内容在视频哪里？")

        self.assertEqual(result.plan.intent_type, IntentType.SEEK_VIDEO)
        self.assertEqual(result.tool_results[0].payload["seek_seconds"], 320)

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

    def test_agent_service_replans_from_series_discovery_into_video_inspection(self) -> None:
        class SequentialGateway(FakeGateway):
            def __init__(self) -> None:
                super().__init__()
                self.call_count = 0

            def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
                if not self._is_planner_call(messages):
                    return "这是最终回答"
                self.structured_calls.append(messages)
                self.response_models.append(PlannerActionPlan)
                self.call_count += 1
                if self.call_count == 1:
                    return self.build_planner_completion_from_plan(
                        "先列出系列视频，再挑选候选",
                        {
                            "intent_type": "series_answer",
                            "scope_type": "series",
                            "tool_calls": [
                                {"tool_name": "list_series_videos"},
                                {"tool_name": "add_series_candidates", "video_ids": ["video-1"], "reason": "先看这期"},
                            ],
                            "reason": "先列出系列视频，再挑选候选",
                            "assistant_message": "",
                            "out_of_scope_reason": "",
                        },
                    )
                if self.call_count == 2:
                    return self.build_planner_completion_from_plan(
                        "现在读取候选视频概况",
                        {
                            "intent_type": "series_answer",
                            "scope_type": "series",
                            "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-1"}],
                            "reason": "现在读取候选视频概况",
                            "assistant_message": "",
                            "out_of_scope_reason": "",
                        },
                    )
                return self.build_planner_completion_from_plan(
                    "证据已经足够，可以回答",
                    {
                        "intent_type": "series_answer",
                        "scope_type": "series",
                        "tool_calls": [],
                        "reason": "证据已经足够，可以回答",
                        "assistant_message": "",
                        "out_of_scope_reason": "",
                    },
                )

        executed_calls: list[str] = []

        def fake_list_series_videos(call, context):
            del call, context
            executed_calls.append("list_series_videos")
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "series_title": "Series A",
                    "videos": [{"video_id": "video-1", "title": "Video 1", "processed": True, "status": "ready"}],
                },
            )

        def fake_add_series_candidates(call, context):
            del context
            executed_calls.append("add_series_candidates")
            return ToolExecutionResult(
                tool_name=ToolName.ADD_SERIES_CANDIDATES,
                status="ok",
                payload={
                    "candidate_buffer": [
                        {
                            "video_id": "video-1",
                            "title": "Video 1",
                            "processed": True,
                            "status": "ready",
                            "reason": call.reason,
                        }
                    ]
                },
            )

        def fake_get_video_summary(call, context):
            del context
            executed_calls.append(f"get_video_summary:{call.video_id}")
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "video_id": call.video_id,
                    "title": "Video 1",
                    "generated": True,
                    "one_sentence_summary": "summary ready",
                },
            )

        service = AgentService(
            gateway=SequentialGateway(),
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
                    ToolName.ADD_SERIES_CANDIDATES: fake_add_series_candidates,
                    ToolName.GET_VIDEO_SUMMARY: fake_get_video_summary,
                }
            ),
        )

        result = service.run("series|series-a|series-home", "这个系列主要讲了哪些主题？")

        self.assertEqual(
            executed_calls,
            ["list_series_videos", "add_series_candidates", "get_video_summary:video-1"],
        )
        self.assertEqual(result.tool_results[-1].payload["video_id"], "video-1")

    def test_executor_guard_blocks_deep_tools_before_candidate_selection(self) -> None:
        executor = RegistryAgentToolExecutor(registry={})
        with self.assertRaises(AgentPlanError):
            executor.execute_call(
                AgentActionPlan.model_validate(
                    {
                        "intent_type": "series_answer",
                        "scope_type": "series",
                        "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-1"}],
                        "reason": "错误读取",
                    }
                ).tool_calls[0],
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                    inspection_stage=InspectionStage.SERIES_DISCOVERY,
                ),
            )

    def test_responder_input_view_preserves_unknown_payload_fields(self) -> None:
        view = _build_responder_input_view(
            user_message="看看用户画像",
            plan=AgentActionPlan.model_validate(
                {
                    "intent_type": "answer_question",
                    "scope_type": "video",
                    "tool_calls": [],
                    "reason": "直接回答",
                }
            ),
            tool_results=[
                ToolExecutionResult(
                    tool_name=ToolName.GET_VIDEO_TOOLS,
                    status="ok",
                    payload={
                        "user_name": "alice",
                        "preference": "deep-dive",
                    },
                )
            ],
        )

        self.assertEqual(view.tool_facts[0].payload["user_name"], "alice")
        self.assertEqual(view.tool_facts[0].payload["preference"], "deep-dive")

    def test_validate_action_plan_rejects_missing_seek_seconds(self) -> None:
        with self.assertRaises(Exception):
            validate_action_plan(
                AgentActionPlan.model_validate(
                    {
                        "intent_type": IntentType.SEEK_VIDEO,
                        "scope_type": ScopeType.VIDEO,
                        "assistant_message": "",
                        "tool_calls": [{"tool_name": "video_seek"}],
                        "reason": "",
                        "out_of_scope_reason": "",
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
        class TwoStepGateway(FakeGateway):
            def __init__(self) -> None:
                super().__init__()
                self.call_count = 0

            def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
                if not self._is_planner_call(messages):
                    return "最终回答"
                self.structured_calls.append(messages)
                self.response_models.append(PlannerActionPlan)
                self.call_count += 1
                if self.call_count == 1:
                    return self.build_planner_completion_from_plan(
                        "先加入候选",
                        {
                            "intent_type": "series_answer",
                            "scope_type": "series",
                            "tool_calls": [{"tool_name": "add_series_candidates", "video_ids": ["video-1"], "reason": "加入候选"}],
                            "reason": "先加入候选",
                            "assistant_message": "",
                            "out_of_scope_reason": "",
                        },
                    )
                if self.call_count == 2:
                    return self.build_planner_completion_from_plan(
                        "现在读取候选概况",
                        {
                            "intent_type": "series_answer",
                            "scope_type": "series",
                            "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-1"}],
                            "reason": "现在读取候选概况",
                            "assistant_message": "",
                            "out_of_scope_reason": "",
                        },
                    )
                return self.build_planner_completion_from_plan(
                    "证据已经足够，可以回答",
                    {
                        "intent_type": "series_answer",
                        "scope_type": "series",
                        "tool_calls": [],
                        "reason": "证据已经足够，可以回答",
                        "assistant_message": "",
                        "out_of_scope_reason": "",
                    },
                )

        def fake_add_series_candidates(call, context):
            del context
            return ToolExecutionResult(
                tool_name=ToolName.ADD_SERIES_CANDIDATES,
                status="ok",
                payload={
                    "candidate_buffer": [
                        {"video_id": "video-1", "title": "Video 1", "processed": True, "status": "ready", "reason": call.reason}
                    ]
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
            gateway=TwoStepGateway(),
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
                    ToolName.ADD_SERIES_CANDIDATES: fake_add_series_candidates,
                    ToolName.GET_VIDEO_SUMMARY: fake_get_video_summary,
                }
            ),
        )

        service.run("series|series-a|series-home", "这个系列主要讲了哪些主题？")
        snapshot = store.get_snapshot("series|series-a|series-home")

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.context.inspection_stage, InspectionStage.ANSWER_READY)
        self.assertEqual(snapshot.context.candidate_buffer[0].video_id, "video-1")
        self.assertEqual(snapshot.context.inspected_video_ids, ["video-1"])


if __name__ == "__main__":
    unittest.main()
