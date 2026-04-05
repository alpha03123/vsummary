from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.agent.execution import RegistryAgentToolExecutor
from backend.agent.agent.planner import _convert_planner_plan, extract_action_plan
from backend.agent.agent.responder import _build_responder_user_message
from backend.agent.agent.service import AgentService
from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import InMemoryAgentMemoryStore
from backend.agent.schemas.action_plan import AgentActionPlan, IntentType, PlannerActionPlan, ScopeType
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName, VideoSeekCall
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.plan import validate_action_plan


class FakeGateway:
    def __init__(self) -> None:
        self.structured_calls: list[list[AgentChatMessage]] = []
        self.response_models: list[type] = []

    def create_structured_completion(self, messages: list[AgentChatMessage], response_model):
        self.structured_calls.append(messages)
        self.response_models.append(response_model)
        return response_model.model_validate(
            {
                "intent_type": "seek_video",
                "scope_type": "video",
                "assistant_message": "",
                "tool_calls": [
                    {
                        "tool_name": "video_seek",
                        "seek_seconds": 320,
                    }
                ],
                "reason": "用户在问具体时间点",
                "out_of_scope_reason": "",
            }
        )

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        return "## 定位结果\n\n这个内容大约在 05:20，可以直接看视频。"


def fake_video_seek(call: VideoSeekCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.VIDEO_SEEK,
        status="ok",
        payload={
            "selected_tool": "video",
            "seek_seconds": call.seek_seconds,
        },
    )


class AgentScaffoldTests(unittest.TestCase):
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
                )
            )

    def test_agent_service_executes_tool_calls(self) -> None:
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
        self.assertEqual(result.assistant_message, "## 定位结果\n\n这个内容大约在 05:20，可以直接看视频。")
        self.assertEqual(result.plan.tool_calls[0].seek_seconds, 320)
        self.assertEqual(result.tool_results[0].payload["selected_tool"], "video")
        self.assertEqual(result.tool_results[0].payload["seek_seconds"], 320)

    def test_agent_memory_is_shared_within_same_series(self) -> None:
        gateway = FakeGateway()
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
                    ToolName.VIDEO_SEEK: fake_video_seek,
                }
            ),
        )

        service.run_with_context(
            session_id="video|series-a|video-1|studio",
            user_message="先记住这个系列背景",
            context_override=AgentContext(
                session_id="video|series-a|video-1|studio",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
                selected_tool="studio",
            ),
        )
        service.run_with_context(
            session_id="video|series-a|video-2|overview",
            user_message="这个系列后面提到哪里了？",
            context_override=AgentContext(
                session_id="video|series-a|video-2|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-2",
                selected_tool="overview",
            ),
        )

        second_call_messages = gateway.structured_calls[-1]
        self.assertTrue(any(message.content == "先记住这个系列背景" for message in second_call_messages))

    def test_responder_message_uses_fact_view_instead_of_plan_dump(self) -> None:
        message = _build_responder_user_message(
            user_message="这个内容在视频哪里？",
            plan=AgentActionPlan.model_validate(
                {
                    "intent_type": "seek_video",
                    "scope_type": "video",
                    "tool_calls": [{"tool_name": "video_seek", "seek_seconds": 320}],
                    "reason": "定位时间点",
                }
            ),
            tool_results=[
                ToolExecutionResult(
                    tool_name=ToolName.VIDEO_SEEK,
                    status="ok",
                    payload={
                        "selected_tool": "video",
                        "seek_seconds": 320,
                        "chapter_title": "准备工作",
                    },
                )
            ],
        )

        self.assertIn('"answer_goal"', message)
        self.assertIn('"tool_facts"', message)
        self.assertIn('"payload"', message)
        self.assertNotIn("规划结果", message)

    def test_series_answer_allows_information_tool_chain(self) -> None:
        plan = validate_action_plan(
            AgentActionPlan.model_validate(
                {
                    "intent_type": "series_answer",
                    "scope_type": "series",
                    "tool_calls": [
                        {"tool_name": "list_series_videos"},
                        {"tool_name": "get_video_summary", "video_id": "video-1"},
                        {"tool_name": "get_video_summary", "video_id": "video-2"},
                    ],
                    "reason": "需要先收集系列下的视频概况",
                }
            )
        )

        self.assertEqual(len(plan.tool_calls), 3)
        self.assertEqual(plan.tool_calls[0].tool_name, ToolName.LIST_SERIES_VIDEOS)

    def test_series_answer_rejects_more_than_three_information_tools(self) -> None:
        with self.assertRaises(AgentPlanError):
            validate_action_plan(
                AgentActionPlan.model_validate(
                    {
                        "intent_type": "series_answer",
                        "scope_type": "series",
                        "tool_calls": [
                            {"tool_name": "list_series_videos"},
                            {"tool_name": "get_video_summary", "video_id": "video-1"},
                            {"tool_name": "get_video_summary", "video_id": "video-2"},
                            {"tool_name": "get_video_summary", "video_id": "video-3"},
                        ],
                        "reason": "步骤过多",
                    }
                )
            )

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
        self.assertEqual(plan.tool_calls[0].seek_seconds, 320)

    def test_planner_action_plan_schema_avoids_one_of(self) -> None:
        planner_schema = PlannerActionPlan.model_json_schema()
        schema_text = str(planner_schema)

        self.assertNotIn("oneOf", schema_text)

    def test_convert_planner_plan_maps_flat_tool_call_into_runtime_tool_call(self) -> None:
        planner_plan = PlannerActionPlan.model_validate(
            {
                "intent_type": "series_answer",
                "scope_type": "series",
                "tool_calls": [
                    {"tool_name": "list_series_videos", "series_id": "series-a"},
                    {"tool_name": "get_video_summary", "series_id": "series-a", "video_id": "video-1"},
                ],
                "reason": "先列出视频，再读概况",
            }
        )

        runtime_plan = _convert_planner_plan(planner_plan)

        self.assertEqual(runtime_plan.tool_calls[0].tool_name, ToolName.LIST_SERIES_VIDEOS)
        self.assertEqual(runtime_plan.tool_calls[1].tool_name, ToolName.GET_VIDEO_SUMMARY)


if __name__ == "__main__":
    unittest.main()
