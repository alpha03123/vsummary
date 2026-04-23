from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext
from backend.agent_graph.runtime.service import AgentGraphService
from backend.api.bootstrap import LazyAgentRuntimeProvider, build_api_container
from backend.agent.schemas.stream_events import AgentStreamEvent


class _FakeGraph:
    def invoke(self, payload):
        return {
            **payload,
            "answer": "graph answer",
            "assistant_message": "graph finalized answer",
            "retrieval_results": [
                {
                    "video_id": "video-1",
                    "title": "Video 1",
                    "source_type": "summary",
                    "snippet": "这是摘要证据。",
                }
            ],
        }

    def stream(self, payload, *, stream_mode=None, **kwargs):
        del kwargs
        if stream_mode != "debug":
            raise AssertionError("expected debug stream mode")
        base = {
            **payload,
            "tasks": [
                {
                    "task_id": "task-1",
                    "instruction": payload["user_message"],
                    "depends_on": [],
                    "kind_hint": "",
                }
            ],
            "current_task_index": 0,
            "current_task": {
                "task_id": "task-1",
                "instruction": payload["user_message"],
                "depends_on": [],
                "kind_hint": "",
            },
            "current_task_context": {"dependencies": [], "latest_answer": ""},
            "task_outputs": [],
        }
        states = [
            (
                "decompose",
                base,
                "2026-04-18T07:00:00+00:00",
                "2026-04-18T07:00:00.010000+00:00",
            ),
            (
                "build_plan",
                {
                    **base,
                    "query_plan": {"goal": "question", "subplans": []},
                    "current_subplan_index": -1,
                    "current_subplan": {},
                    "tool_results": [],
                    "retrieval_results": [
                        {
                            "video_id": "video-1",
                            "title": "Video 1",
                            "source_type": "summary",
                            "snippet": "这是摘要证据。",
                        }
                    ],
                },
                "2026-04-18T07:00:00.010000+00:00",
                "2026-04-18T07:00:00.030000+00:00",
            ),
            (
                "answer",
                {
                    **base,
                    "query_plan": {"goal": "question", "subplans": []},
                    "current_subplan_index": -1,
                    "current_subplan": {},
                    "tool_results": [],
                    "retrieval_results": [
                        {
                            "video_id": "video-1",
                            "title": "Video 1",
                            "source_type": "summary",
                            "snippet": "这是摘要证据。",
                        }
                    ],
                    "task_outputs": [
                        {
                            "task_id": "task-1",
                            "kind": "answer",
                            "value": "graph answer",
                        }
                    ],
                    "answer": "graph answer",
                },
                "2026-04-18T07:00:00.030000+00:00",
                "2026-04-18T07:00:00.050000+00:00",
            ),
            (
                "finalize",
                {
                    **base,
                    "query_plan": {"goal": "question", "subplans": []},
                    "current_subplan_index": -1,
                    "current_subplan": {},
                    "tool_results": [],
                    "retrieval_results": [
                        {
                            "video_id": "video-1",
                            "title": "Video 1",
                            "source_type": "summary",
                            "snippet": "这是摘要证据。",
                        }
                    ],
                    "task_outputs": [
                        {
                            "task_id": "task-1",
                            "kind": "answer",
                            "value": "graph answer",
                        }
                    ],
                    "answer": "graph answer",
                    "assistant_message": "graph finalized answer",
                },
                "2026-04-18T07:00:00.050000+00:00",
                "2026-04-18T07:00:00.060000+00:00",
            ),
            (
                "update_memory",
                {
                    **base,
                    "query_plan": {"goal": "question", "subplans": []},
                    "current_subplan_index": -1,
                    "current_subplan": {},
                    "tool_results": [],
                    "retrieval_results": [
                        {
                            "video_id": "video-1",
                            "title": "Video 1",
                            "source_type": "summary",
                            "snippet": "这是摘要证据。",
                        }
                    ],
                    "task_outputs": [
                        {
                            "task_id": "task-1",
                            "kind": "answer",
                            "value": "graph answer",
                        }
                    ],
                    "answer": "graph answer",
                    "assistant_message": "graph finalized answer",
                    "history_summary_update": "memory updated",
                },
                "2026-04-18T07:00:00.060000+00:00",
                "2026-04-18T07:00:00.070000+00:00",
            ),
        ]
        for index, (node_name, result_state, start_ts, end_ts) in enumerate(states, start=1):
            stage_id = f"stage-{index}"
            yield {
                "step": index,
                "timestamp": start_ts,
                "type": "task",
                "payload": {
                    "id": stage_id,
                    "name": node_name,
                    "input": payload,
                },
            }
            yield {
                "step": index,
                "timestamp": end_ts,
                "type": "task_result",
                "payload": {
                    "id": stage_id,
                    "name": node_name,
                    "error": None,
                    "result": result_state,
                    "interrupts": [],
                },
            }


class _InterruptBeforeAnswerGraph:
    def invoke(self, payload, interrupt_before=None):
        if interrupt_before == ["answer"]:
            return {
                **payload,
                "tasks": [
                    {
                        "task_id": "task-1",
                        "instruction": payload["user_message"],
                        "depends_on": [],
                        "kind_hint": "",
                    }
                ],
                "current_task_index": 0,
                "current_task": {
                    "task_id": "task-1",
                    "instruction": payload["user_message"],
                    "depends_on": [],
                    "kind_hint": "",
                },
                "current_task_context": {"dependencies": [], "latest_answer": ""},
                "query_plan": {"goal": "question", "subplans": []},
                "retrieval_results": [
                    {
                        "video_id": "video-1",
                        "title": "Video 1",
                        "source_type": "summary",
                        "snippet": "这是摘要证据。",
                    }
                ],
                "tool_results": [],
                "task_outputs": [],
                "history_messages": [],
            }
        return {
            **payload,
            "answer": "graph answer",
            "assistant_message": "graph finalized answer",
        }

    def stream(self, payload, *, stream_mode=None, interrupt_before=None, **kwargs):
        del kwargs
        if stream_mode != "debug":
            raise AssertionError("expected debug stream mode")
        base = self.invoke(payload, interrupt_before=interrupt_before)
        states = [
            ("decompose", base, "2026-04-18T07:00:00+00:00", "2026-04-18T07:00:00.010000+00:00"),
            ("build_plan", base, "2026-04-18T07:00:00.010000+00:00", "2026-04-18T07:00:00.030000+00:00"),
        ]
        for index, (node_name, result_state, start_ts, end_ts) in enumerate(states, start=1):
            stage_id = f"pre-answer-stage-{index}"
            yield {
                "step": index,
                "timestamp": start_ts,
                "type": "task",
                "payload": {"id": stage_id, "name": node_name, "input": payload},
            }
            yield {
                "step": index,
                "timestamp": end_ts,
                "type": "task_result",
                "payload": {"id": stage_id, "name": node_name, "error": None, "result": result_state, "interrupts": []},
            }


class _StreamingAggregator:
    def stream(self, **kwargs):
        del kwargs
        from backend.agent.schemas.chat_stream import ChatCompletionStreamChunk

        yield ChatCompletionStreamChunk(delta="这是")
        yield ChatCompletionStreamChunk(delta="真实流式回答。")
        yield ChatCompletionStreamChunk(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})


class _MemoryUpdateProgram:
    def run(self, **kwargs):
        del kwargs
        return "memory updated"


class _VideoGraph:
    def invoke(self, payload):
        return {
            **payload,
            "answer": "video answer",
            "assistant_message": "video finalized answer",
            "retrieval_results": [
                {
                    "depth": "summary",
                    "items": [
                        {
                            "video_id": payload.get("video_id", "video-1"),
                            "title": "Video 1",
                            "source_type": "summary",
                            "snippet": "这是视频摘要。",
                        }
                    ],
                }
            ],
        }

    def stream(self, payload, *, stream_mode=None, **kwargs):
        del kwargs
        if stream_mode != "debug":
            raise AssertionError("expected debug stream mode")
        states = [
            ("route_video_request", self.invoke(payload), "2026-04-18T07:00:00+00:00", "2026-04-18T07:00:00.010000+00:00"),
            ("load_video_summary", self.invoke(payload), "2026-04-18T07:00:00.010000+00:00", "2026-04-18T07:00:00.020000+00:00"),
            ("answer", self.invoke(payload), "2026-04-18T07:00:00.020000+00:00", "2026-04-18T07:00:00.030000+00:00"),
            ("finalize", self.invoke(payload), "2026-04-18T07:00:00.030000+00:00", "2026-04-18T07:00:00.040000+00:00"),
        ]
        for index, (node_name, result_state, start_ts, end_ts) in enumerate(states, start=1):
            stage_id = f"video-stage-{index}"
            yield {
                "step": index,
                "timestamp": start_ts,
                "type": "task",
                "payload": {"id": stage_id, "name": node_name, "input": payload},
            }
            yield {
                "step": index,
                "timestamp": end_ts,
                "type": "task_result",
                "payload": {"id": stage_id, "name": node_name, "error": None, "result": result_state, "interrupts": []},
            }


class AgentGraphServiceTests(unittest.TestCase):
    def test_agent_graph_service_runs_graph_with_loaded_context(self) -> None:
        service = AgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                )
            ),
            graph=_FakeGraph(),
        )

        result = service.run(
            session_id="series|series-a|series-home",
            user_message="这个系列主要讲了什么？",
        )

        self.assertEqual(result.assistant_message, "graph finalized answer")
        self.assertEqual(result.citations[0].source_type, "summary")
        self.assertEqual(result.citations[0].slots[0].video_id, "video-1")

    def test_run_with_context_uses_context_override_for_graph_input(self) -> None:
        captured = {}

        class _CapturingGraph:
            def invoke(self, payload):
                captured.update(payload)
                return {
                    **payload,
                    "assistant_message": "ok",
                    "answer": "fallback",
                }

        service = AgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                )
            ),
            graph=_CapturingGraph(),
        )

        result = service.run_with_context(
            session_id="series|series-a|series-home",
            user_message="这个系列主要讲了什么？",
            context_override=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
                video_title="Video 1",
            ),
        )

        self.assertEqual(result.assistant_message, "ok")
        self.assertEqual(captured["scope_type"], "video")
        self.assertEqual(captured["video_id"], "video-1")

    def test_bootstrap_can_build_agent_graph_service(self) -> None:
        with patch("backend.api.bootstrap.SeriesRetrievalService", return_value=object()):
            container = build_api_container(ROOT)

            service = container.get_agent_graph_service()

        self.assertIsNotNone(service)

    def test_bootstrap_exposes_graph_components_for_profiling(self) -> None:
        fake_retrieval_service = object()
        fake_meta_state_reader = object()
        fake_action_dispatcher = object()
        with (
            patch("backend.api.bootstrap.SeriesRetrievalService", return_value=fake_retrieval_service),
            patch("backend.api.bootstrap.MetaStateReader", return_value=fake_meta_state_reader),
            patch("backend.api.bootstrap.ActionDispatcher", return_value=fake_action_dispatcher),
        ):
            container = build_api_container(ROOT)
            service = container.get_agent_graph_service()

        self.assertTrue(hasattr(service, "_decomposer_program"))
        self.assertTrue(hasattr(service, "_classifier_program"))
        self.assertTrue(hasattr(service, "_compare_split_program"))
        self.assertIs(service._retrieval_service, fake_retrieval_service)
        self.assertTrue(hasattr(service, "_pinpoint_service"))
        self.assertIs(service._meta_state_reader, fake_meta_state_reader)
        self.assertIs(service._action_dispatcher, fake_action_dispatcher)

    def test_lazy_provider_loads_compiled_split_compare_program(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config" / "settings.toml").write_text("", encoding="utf-8")
            (root / ".env").write_text("OPENAI_API_KEY=test-key\nOPENAI_MODEL=gpt-5.4\n", encoding="utf-8")

            provider = LazyAgentRuntimeProvider(
                root_dir=root,
                workspace=SimpleNamespace(),
            )
            fake_settings = SimpleNamespace(
                agent_context=SimpleNamespace(
                    window_tokens=1000,
                    reserved_output_tokens=100,
                    warning_threshold_ratio=0.7,
                    compact_threshold_ratio=0.8,
                    blocking_threshold_ratio=0.9,
                ),
                agent_retrieval=SimpleNamespace(
                    embedding_device="cpu",
                ),
            )
            with (
                patch(
                    "backend.api.bootstrap.load_env_settings",
                    return_value=SimpleNamespace(
                        provider="openai_compatible",
                        api_key="test-key",
                        model="gpt-5.4",
                        base_url="http://127.0.0.1:8317/v1",
                    ),
                ),
                patch("backend.api.bootstrap.normalize_openai_base_url", return_value="http://127.0.0.1:8317/v1"),
                patch("backend.api.bootstrap.dspy.configure"),
                patch("backend.api.bootstrap.ProxyStreamingLM"),
                patch("backend.api.bootstrap.load_settings", return_value=fake_settings),
                patch("backend.api.bootstrap.create_list_series_videos_handler", return_value=object()),
                patch("backend.api.bootstrap.create_get_video_summary_handler", return_value=object()),
                patch("backend.api.bootstrap.create_get_video_tools_handler", return_value=object()),
                patch("backend.api.bootstrap.create_get_video_transcript_handler", return_value=object()),
                patch("backend.api.bootstrap._build_tool_executor", return_value=object()),
                patch("backend.api.bootstrap.SeriesRetrievalService", return_value=object()),
                patch("backend.api.bootstrap.MetaStateReader", return_value=object()),
                patch("backend.api.bootstrap.ActionDispatcher", return_value=object()),
                patch("backend.api.bootstrap.load_or_create_decompose_program", return_value="decompose-program"),
                patch("backend.api.bootstrap.load_or_create_classifier_program", return_value="classifier-program"),
                patch("backend.api.bootstrap.load_or_create_split_compare_program", return_value="split-program") as split_loader,
                patch("backend.api.bootstrap.LegacyStyleSeriesPlanner", return_value="series-planner"),
                patch("backend.api.bootstrap.build_agent_graph", return_value=_FakeGraph()) as build_graph,
            ):
                provider.get_agent_graph_service()

            split_loader.assert_called_once_with(
                artifact_path=root / "data" / "agent_graph" / "dspy" / "split_compare" / "program.json",
            )
            self.assertEqual(build_graph.call_args.kwargs["compare_split_program"], "split-program")

    def test_graph_service_streams_basic_events(self) -> None:
        service = AgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                )
            ),
            graph=_FakeGraph(),
        )

        events = list(
            service.stream_with_context(
                session_id="series|series-a|series-home",
                user_message="这个系列主要讲了什么？",
                context_override=None,
            )
        )

        self.assertTrue(all(isinstance(event, AgentStreamEvent) for event in events))
        self.assertIn("stage_started", [event.type for event in events])
        self.assertIn("stage_completed", [event.type for event in events])
        self.assertIn("answer_delta", [event.type for event in events])
        self.assertIn("answer_completed", [event.type for event in events])
        self.assertEqual(
            events[1].payload,
            {
                "stage_id": "stage-1",
                "node_id": "decompose",
                "label": "拆解任务",
            },
        )

    def test_graph_service_streams_true_series_answer_with_usage(self) -> None:
        service = AgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                )
            ),
            graph=_InterruptBeforeAnswerGraph(),
            series_aggregator=_StreamingAggregator(),
            memory_update_program=_MemoryUpdateProgram(),
        )

        events = list(
            service.stream_with_context(
                session_id="series|series-a|series-home",
                user_message="这个系列主要讲了什么？",
                context_override=None,
            )
        )

        self.assertIn(
            {
                "stage_id": "stage-answer",
                "node_id": "answer",
                "label": "生成回答",
            },
            [event.payload for event in events if event.type == "stage_started"],
        )
        self.assertEqual(
            [event.payload["delta"] for event in events if event.type == "answer_delta"],
            ["这是", "真实流式回答。"],
        )
        answer_completed = next(event for event in events if event.type == "answer_completed")
        self.assertEqual(answer_completed.payload["message"], "这是真实流式回答。")
        self.assertEqual(answer_completed.payload["usage"]["total_tokens"], 15)

    def test_graph_service_uses_video_graph_for_video_scope_stream(self) -> None:
        service = AgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="video|series-a|video-1|overview",
                    scope_type="video",
                    series_id="series-a",
                    video_id="video-1",
                )
            ),
            graph=_FakeGraph(),
            video_graph=_VideoGraph(),
        )

        events = list(
            service.stream_with_context(
                session_id="video|series-a|video-1|overview",
                user_message="这个视频主要讲了什么？",
            )
        )

        stage_nodes = [event.payload["node_id"] for event in events if event.type == "stage_started"]
        self.assertEqual(stage_nodes[:2], ["route_video_request", "load_video_summary"])
        self.assertNotIn("decompose", stage_nodes)


if __name__ == "__main__":
    unittest.main()
