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
from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent_graph.runtime.graph import build_agent_graph
from backend.agent_graph.runtime.service import AgentGraphService
from backend.api.bootstrap import LazyAgentRuntimeProvider, build_api_container


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
        states = [
            (
                "build_plan",
                {
                    **payload,
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
                "2026-04-18T07:00:00+00:00",
                "2026-04-18T07:00:00.020000+00:00",
            ),
            (
                "answer",
                {
                    **payload,
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
                            "task_id": "",
                            "kind": "answer",
                            "value": "graph answer",
                        }
                    ],
                    "answer": "graph answer",
                },
                "2026-04-18T07:00:00.020000+00:00",
                "2026-04-18T07:00:00.040000+00:00",
            ),
            (
                "finalize",
                {
                    **payload,
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
                            "task_id": "",
                            "kind": "answer",
                            "value": "graph answer",
                        }
                    ],
                    "answer": "graph answer",
                    "assistant_message": "graph finalized answer",
                },
                "2026-04-18T07:00:00.040000+00:00",
                "2026-04-18T07:00:00.050000+00:00",
            ),
            (
                "update_memory",
                {
                    **payload,
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
                            "task_id": "",
                            "kind": "answer",
                            "value": "graph answer",
                        }
                    ],
                    "answer": "graph answer",
                    "assistant_message": "graph finalized answer",
                    "history_summary_update": "memory updated",
                },
                "2026-04-18T07:00:00.050000+00:00",
                "2026-04-18T07:00:00.060000+00:00",
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
        stage_id = "pre-answer-stage-1"
        yield {
            "step": 1,
            "timestamp": "2026-04-18T07:00:00+00:00",
            "type": "task",
            "payload": {"id": stage_id, "name": "build_plan", "input": payload},
        }
        yield {
            "step": 1,
            "timestamp": "2026-04-18T07:00:00.020000+00:00",
            "type": "task_result",
            "payload": {"id": stage_id, "name": "build_plan", "error": None, "result": base, "interrupts": []},
        }


class _StreamingAggregator:
    def stream(self, **kwargs):
        del kwargs
        from backend.agent.schemas.chat_stream import ChatCompletionStreamChunk

        yield ChatCompletionStreamChunk(delta="这是")
        yield ChatCompletionStreamChunk(delta="真实流式回答。")
        yield ChatCompletionStreamChunk(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})


class _SaveNoteClassifier:
    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = "", history_summary: str = "", history_selected_videos=None):
        del user_message, scope_type, series_id, video_id, history_summary, history_selected_videos
        from backend.agent_graph.query.models import StructuredQueryPlan

        return StructuredQueryPlan(
            goal="action",
            target_source="all",
            context_need="chunk",
            reason="需要先总结再记笔记。",
            action_name="save_note",
            action_args={"note_type": "key_points"},
        )


class _NoopSplitCompare:
    def run(self, *, user_message: str):
        del user_message
        from backend.agent_graph.query.models import CompareSplitDecision

        return CompareSplitDecision(queries=[])


class _SummaryAndTranscriptRetrieval:
    def search(self, **kwargs):
        target_source = kwargs["target_source"]
        video_id = kwargs.get("video_id", "video-1")
        if target_source == "summary":
            return {
                "hits": [
                    {
                        "video_id": video_id,
                        "title": "Video 1",
                        "source_type": "summary",
                        "source_family": "summary",
                        "snippet": "这是摘要证据。",
                    }
                ]
            }
        return {
            "hits": [
                {
                    "video_id": video_id,
                    "title": "Video 1",
                    "source_type": "transcript_chunk",
                    "source_family": "transcript",
                    "snippet": "命中片段一",
                },
                {
                    "video_id": video_id,
                    "title": "Video 1",
                    "source_type": "transcript_chunk",
                    "source_family": "transcript",
                    "snippet": "命中片段二",
                },
            ]
        }


class _SaveNoteActionDispatcher:
    def dispatch(self, *, scope_type: str, series_id: str, video_id: str, action_name: str, action_args: dict[str, object]):
        del scope_type, series_id, video_id
        return {
            "message": "我已经帮你记好这条笔记。",
            "tool_results": [
                {
                    "tool_name": action_name,
                    "status": "ok",
                    "payload": dict(action_args),
                }
            ],
        }


class _SummaryAnswer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        del user_message, meta_state
        return f"总结：{retrieval_results[0]['snippet']}"


class _NoteProgram:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        del user_message, meta_state
        return f"## 重点\n- {retrieval_results[0]['snippet']}"


class _ActionReplyProgram:
    def run(self, *, user_message: str, action_name: str, generated_content: str):
        del user_message, action_name, generated_content
        return "已记录当前视频重点，主要涉及摘要里的核心结论。"


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

        result = service.run_turn(session_id="series|series-a|series-home", user_message="这个系列主要讲了什么？")

        self.assertEqual(result.assistant_message, "graph finalized answer")
        self.assertEqual(result.citations[0].source_type, "summary")
        self.assertEqual(result.citations[0].slots[0].video_id, "video-1")

    def test_run_turn_uses_context_override_for_graph_input(self) -> None:
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

        result = service.run_turn(
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

    def test_bootstrap_builds_graph_service_without_component_leaks(self) -> None:
        with (
                patch("backend.api.bootstrap.SeriesRetrievalService", return_value=object()),
                patch("backend.api.bootstrap.MetaStateReader", return_value=object()),
                patch("backend.api.bootstrap.ActionDispatcher", return_value=object()),
                patch("backend.api.bootstrap.SeriesPlanner", return_value="series-planner"),
            ):
                container = build_api_container(ROOT)
                service = container.get_agent_graph_service()

        self.assertIs(service.graph, service._graph)
        self.assertFalse(hasattr(service, "_classifier_program"))
        self.assertFalse(hasattr(service, "_retrieval_service"))

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
                patch("backend.api.bootstrap.SeriesPlanner", return_value="series-planner"),
                patch("backend.api.bootstrap.load_or_create_classifier_program", return_value="classifier-program"),
                patch("backend.api.bootstrap.load_or_create_split_compare_program", return_value="split-program") as split_loader,
                patch("backend.api.bootstrap.build_agent_graph", return_value=_FakeGraph()) as build_graph,
            ):
                provider.get_agent_graph_service()

            split_loader.assert_called_once_with(
                artifact_path=root / "data" / "agent_graph" / "dspy" / "split_compare" / "program.json",
            )
            self.assertEqual(build_graph.call_args.kwargs["series_planner"], "series-planner")
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
        self.assertEqual(events[1].payload["node_id"], "build_plan")

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

    def test_graph_service_uses_single_graph_for_video_scope_stream(self) -> None:
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
        )

        events = list(
            service.stream_with_context(
                session_id="video|series-a|video-1|overview",
                user_message="这个视频主要讲了什么？",
            )
        )

        stage_nodes = [event.payload["node_id"] for event in events if event.type == "stage_started"]
        self.assertEqual(stage_nodes[0], "build_plan")

    def test_graph_service_streams_single_rag_tool_and_visible_save_note_action(self) -> None:
        graph = build_agent_graph(
            classifier_program=_SaveNoteClassifier(),
            compare_split_program=_NoopSplitCompare(),
            retrieval_service=_SummaryAndTranscriptRetrieval(),
            action_dispatcher=_SaveNoteActionDispatcher(),
            answer_program=_SummaryAnswer(),
            note_program=_NoteProgram(),
            action_reply_program=_ActionReplyProgram(),
        )
        service = AgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="video|series-a|video-1|overview",
                    scope_type="video",
                    series_id="series-a",
                    video_id="video-1",
                    video_title="Video 1",
                )
            ),
            graph=graph,
        )

        events = list(
            service.stream_with_context(
                session_id="video|series-a|video-1|overview",
                user_message="帮我记一下这个视频的重点",
            )
        )

        tool_completed = [event.payload for event in events if event.type == "tool_completed"]
        self.assertEqual(
            [payload["tool_name"] for payload in tool_completed],
            ["get_video_summary", "get_video_transcript", "save_note"],
        )
        self.assertEqual(tool_completed[1]["payload"]["result_count"], 2)
        self.assertEqual(tool_completed[2]["payload"]["note_content"], "## 重点\n- 这是摘要证据。")
        answer_completed = next(event for event in events if event.type == "answer_completed")
        self.assertEqual(answer_completed.payload["message"], "已记录当前视频重点，主要涉及摘要里的核心结论。")
        chain_completed = next(event for event in events if event.type == "tool_chain_completed")
        self.assertEqual(chain_completed.payload["count"], 3)


if __name__ == "__main__":
    unittest.main()
