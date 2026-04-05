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
from backend.agent.agent.responder import _build_responder_input_view, _build_responder_user_message
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
        user_message = messages[-1].content
        if "video_seek" in user_message:
            return response_model.model_validate(
                {
                    "intent_type": "answer_question",
                    "scope_type": "video",
                    "assistant_message": "",
                    "tool_calls": [],
                    "reason": "已经拿到定位结果，可以直接回答",
                    "out_of_scope_reason": "",
                }
            )
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

    def create_text_completion_stream(self, messages: list[AgentChatMessage]):
        yield "## 定位结果\n\n"
        yield "这个内容大约在 05:20，可以直接看视频。"


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
        self.assertNotIn('"facts"', message)

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

    def test_answer_question_allows_transcript_lookup_for_evidence_based_answers(self) -> None:
        plan = validate_action_plan(
            AgentActionPlan.model_validate(
                {
                    "intent_type": "answer_question",
                    "scope_type": "video",
                    "tool_calls": [
                        {"tool_name": "get_video_summary", "video_id": "video-1"},
                        {"tool_name": "transcript_lookup", "query": "Jmanus 是怎么跑起来的"},
                    ],
                    "reason": "先看概况，再补原文证据",
                }
            )
        )

        self.assertEqual(plan.tool_calls[0].tool_name, ToolName.GET_VIDEO_SUMMARY)
        self.assertEqual(plan.tool_calls[1].tool_name, ToolName.TRANSCRIPT_LOOKUP)

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

    def test_validate_action_plan_rejects_pending_video_placeholder(self) -> None:
        with self.assertRaises(AgentPlanError):
            validate_action_plan(
                AgentActionPlan.model_validate(
                    {
                        "intent_type": "series_answer",
                        "scope_type": "series",
                        "tool_calls": [
                            {"tool_name": "get_video_summary", "video_id": "*pending_from_list_series_videos*"},
                        ],
                        "reason": "错误地使用了占位值",
                    }
                )
            )

    def test_extract_action_plan_rejects_video_id_that_is_not_in_observed_list(self) -> None:
        class InvalidSeriesGateway(FakeGateway):
            def create_structured_completion(self, messages: list[AgentChatMessage], response_model):
                self.structured_calls.append(messages)
                self.response_models.append(response_model)
                return response_model.model_validate(
                    {
                        "intent_type": "series_answer",
                        "scope_type": "series",
                        "tool_calls": [{"tool_name": "get_video_summary", "video_id": "__FROM_LIST__"}],
                        "reason": "错误地把列表结果当成占位值引用",
                    }
                )

        with self.assertRaises(AgentPlanError):
            extract_action_plan(
                gateway=InvalidSeriesGateway(),
                context=AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                ),
                memory_store=InMemoryAgentMemoryStore(),
                session_id="series|series-a",
                user_message="这个系列主要讲了哪些主题？",
                observed_tool_results=[
                    ToolExecutionResult(
                        tool_name=ToolName.LIST_SERIES_VIDEOS,
                        status="ok",
                        payload={
                            "series_id": "series-a",
                            "series_title": "Series A",
                            "videos": [{"video_id": "video-1", "title": "Video 1"}],
                        },
                    )
                ],
            )

    def test_agent_service_replans_after_observing_tool_results(self) -> None:
        class SequentialGateway(FakeGateway):
            def __init__(self) -> None:
                super().__init__()
                self.retry_count = 0

            def create_structured_completion(self, messages: list[AgentChatMessage], response_model):
                self.structured_calls.append(messages)
                self.response_models.append(response_model)
                user_message = messages[-1].content
                if "上一次规划存在错误" in user_message:
                    return response_model.model_validate(
                        {
                            "intent_type": "series_answer",
                            "scope_type": "series",
                            "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-1"}],
                            "reason": "改用列表里真实存在的 video_id",
                        }
                    )
                if '"tool_name": "get_video_summary"' in user_message:
                    return response_model.model_validate(
                        {
                            "intent_type": "series_answer",
                            "scope_type": "series",
                            "tool_calls": [],
                            "reason": "信息已足够，可以直接回答",
                        }
                    )
                if "list_series_videos" not in user_message:
                    return response_model.model_validate(
                        {
                            "intent_type": "series_answer",
                            "scope_type": "series",
                            "tool_calls": [{"tool_name": "list_series_videos"}],
                            "reason": "先拿到系列视频列表",
                        }
                    )
                if self.retry_count == 0:
                    self.retry_count += 1
                    return response_model.model_validate(
                        {
                            "intent_type": "series_answer",
                            "scope_type": "series",
                            "tool_calls": [{"tool_name": "get_video_summary", "video_id": "__FROM_LIST__"}],
                            "reason": "先取列表里的一个视频概况",
                        }
                    )
                return response_model.model_validate(
                    {
                        "intent_type": "series_answer",
                        "scope_type": "series",
                        "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-1"}],
                        "reason": "已拿到视频列表，继续读取其中一个视频概况",
                    }
                )

        executed_calls: list[str] = []

        def fake_list_series_videos(call, context):
            executed_calls.append(call.tool_name.value)
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "series_title": "Series A",
                    "videos": [{"video_id": "video-1", "title": "Video 1"}],
                },
            )

        def fake_get_video_summary(call, context):
            executed_calls.append(f"{call.tool_name.value}:{call.video_id}")
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "video_id": call.video_id,
                    "title": "Video 1",
                    "generated": True,
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
                    ToolName.GET_VIDEO_SUMMARY: fake_get_video_summary,
                }
            ),
        )

        result = service.run("series|series-a|series-home", "这个系列主要讲了哪些主题？")

        self.assertEqual(executed_calls, ["list_series_videos", "get_video_summary:video-1"])
        self.assertEqual(len(result.tool_results), 2)
        self.assertEqual(result.tool_results[1].payload["video_id"], "video-1")

    def test_agent_service_retry_feedback_forwards_only_generic_wrapper_and_validation_error(self) -> None:
        class RetryFeedbackGateway(FakeGateway):
            def __init__(self) -> None:
                super().__init__()
                self.retry_messages: list[str] = []

            def create_structured_completion(self, messages: list[AgentChatMessage], response_model):
                self.structured_calls.append(messages)
                self.response_models.append(response_model)
                user_message = messages[-1].content
                if "上一次规划存在错误" in user_message:
                    self.retry_messages.append(user_message)
                    return response_model.model_validate(
                        {
                            "intent_type": "series_answer",
                            "scope_type": "series",
                            "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-1"}],
                            "reason": "按错误原因修正",
                        }
                    )
                return response_model.model_validate(
                    {
                        "intent_type": "series_answer",
                        "scope_type": "series",
                        "tool_calls": [{"tool_name": "get_video_summary", "video_id": "__FROM_LIST__"}],
                        "reason": "错误地使用占位值",
                    }
                )

        def fake_list_series_videos(call, context):
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "series_title": "Series A",
                    "videos": [{"video_id": "video-1", "title": "Video 1"}],
                },
            )

        def fake_get_video_summary(call, context):
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "video_id": "video-1",
                    "title": "Video 1",
                    "generated": True,
                },
            )

        gateway = RetryFeedbackGateway()
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

        plan = service._extract_valid_action_plan(
            context=AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
            ),
            memory_key="series|series-a",
            user_message="这个系列主要讲了哪些主题？",
            observed_tool_results=[
                ToolExecutionResult(
                    tool_name=ToolName.LIST_SERIES_VIDEOS,
                    status="ok",
                    payload={
                        "series_id": "series-a",
                        "series_title": "Series A",
                        "videos": [{"video_id": "video-1", "title": "Video 1"}],
                    },
                )
            ],
        )

        self.assertEqual(plan.tool_calls[0].video_id, "video-1")
        self.assertEqual(len(gateway.retry_messages), 1)
        self.assertIn("上一次规划存在错误，请严格根据错误原因重新规划，不要重复相同错误。", gateway.retry_messages[0])
        self.assertIn(
            "get_video_summary / get_video_tools 的 video_id 必须直接使用上一轮 list_series_videos 返回的真实 video_id。",
            gateway.retry_messages[0],
        )
        self.assertNotIn("不要使用占位符、别名或自然语言标记充当 video_id", gateway.retry_messages[0])

    def test_stream_with_context_yields_thinking_and_tool_events_in_order(self) -> None:
        class StreamingGateway(FakeGateway):
            def __init__(self) -> None:
                super().__init__()
                self.call_count = 0

            def create_structured_completion(self, messages: list[AgentChatMessage], response_model):
                self.structured_calls.append(messages)
                self.response_models.append(response_model)
                self.call_count += 1
                if self.call_count == 1:
                    return response_model.model_validate(
                        {
                            "intent_type": "series_answer",
                            "scope_type": "series",
                            "tool_calls": [{"tool_name": "list_series_videos"}],
                            "reason": "先读取系列视频列表",
                        }
                    )
                return response_model.model_validate(
                    {
                        "intent_type": "series_answer",
                        "scope_type": "series",
                        "tool_calls": [],
                        "reason": "信息已经足够，可以直接回答",
                    }
                )

            def create_text_completion_stream(self, messages: list[AgentChatMessage]):
                yield "这是"
                yield "最终回答"

            def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
                return "这是最终回答"

        def fake_list_series_videos(call, context):
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="ok",
                payload={
                    "series_id": "series-a",
                    "series_title": "Series A",
                    "videos": [{"video_id": "video-1", "title": "Video 1"}],
                },
            )

        service = AgentService(
            gateway=StreamingGateway(),
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
                }
            ),
        )

        events = list(
            service.stream_with_context(
                session_id="series|series-a|series-home",
                user_message="这个系列主要讲了哪些主题？",
                context_override=AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                    selected_tool="series-home",
                ),
            )
        )

        event_types = [event.type for event in events]
        self.assertEqual(event_types[0], "thinking_started")
        self.assertIn("thinking_delta", event_types)
        self.assertLess(event_types.index("thinking_delta"), event_types.index("thinking_completed"))
        self.assertLess(event_types.index("thinking_completed"), event_types.index("tool_started"))
        self.assertLess(event_types.index("tool_started"), event_types.index("tool_completed"))
        self.assertLess(event_types.index("tool_completed"), event_types.index("tool_chain_completed"))
        self.assertIn("answer_started", event_types)
        self.assertIn("answer_delta", event_types)
        self.assertIn("answer_completed", event_types)


if __name__ == "__main__":
    unittest.main()
