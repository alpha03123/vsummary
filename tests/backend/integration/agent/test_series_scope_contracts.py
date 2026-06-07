from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests import _path_setup

ROOT = _path_setup.REPO_ROOT

from backend.agent_graph.query.models import (
    RetrievalHit,
    SeriesAnswerPayload,
    SeriesQueryUnderstanding,
)
from backend.agent_graph.query.series_answer_synthesizer import SeriesAnswerSynthesizer
from backend.agent_graph.query.series_query_processor import SeriesQueryProcessor
from backend.agent_graph.runtime.graph import build_agent_graph
from backend.agent_graph.runtime.service import AgentGraphService
from backend.agent_graph.runtime.turns import AgentGraphTurnBuilder
from backend.agent_graph.runtime.turns import AgentGraphInputBuilder
from backend.agent_graph.runtime.session_recorder import AgentGraphSessionRecorder
from backend.agent_graph.evidence.inline_citations import extract_inline_source_numbers, resolve_inline_citations
from backend.video_summary.tool_executor import RegistryAgentToolExecutor
from backend.agent.memory.context import AgentContext
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.chat_stream import ChatCompletionStreamChunk
from backend.agent.schemas.action_plan import ScopeType
from backend.agent.schemas.tool_calls import (
    OpenNotesCall,
    SaveNoteCall,
    ToolName,
    VideoSeekCall,
)
from backend.agent.session.models import AgentSessionMessageEntry, AgentSessionSnapshot
from backend.agent.session.store import FileAgentSessionStore
from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.video_summary.tools.notes import execute_save_note
from backend.video_summary.tools.notes import execute_open_notes
from backend.video_summary.tools.video import execute_video_seek
from backend.agent_graph.actions.video_action_planner import (
    VideoActionPlanner,
    VideoActionPlannerPayload,
)
from backend.agent_graph.prompts import VIDEO_ACTION_PLANNER_SYSTEM_PROMPT
from backend.api.responses import AgentChatResponse
from backend.shared.llm.json_mode import validate_json_response
from backend.video_summary.tools.notes import SAVE_NOTE_TOOL
from backend.video_summary.library.models import TranscriptSegmentDTO, VideoSummaryDTO, VideoTranscriptDTO


class SeriesScopeContractTests(unittest.TestCase):
    def test_series_query_processor_returns_minimal_contract(self) -> None:
        processor = SeriesQueryProcessor(gateway=FakeQueryGateway())
        debug_trace: dict[str, object] = {}

        result = processor.run(
            user_message="这个系列讲了啥",
            series_id="series-1",
            series_title="Series 1",
            series_catalog={"series_id": "series-1", "videos": []},
            memory_messages=[],
            debug_trace=debug_trace,
        )

        self.assertIsInstance(result, SeriesQueryUnderstanding)
        self.assertEqual(result.filters, {"series_id": "series-1"})
        self.assertEqual(result.normalized_query, "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？")
        self.assertEqual(
            result.subqueries,
            ["这个系列主要讲哪些主题", "这个系列的学习顺序是什么"],
        )
        self.assertIn("series_query_processor", debug_trace)

    def test_series_query_processor_supports_concept_contract_case(self) -> None:
        processor = SeriesQueryProcessor(gateway=FakeConceptQueryGateway())

        result = processor.run(
            user_message="Copilot 模式是啥",
            series_id="series-1",
            series_title="Series 1",
            series_catalog={"series_id": "series-1", "videos": []},
            memory_messages=[],
        )

        self.assertEqual(result.filters, {"series_id": "series-1"})
        self.assertIn("Copilot 模式", result.normalized_query)

    def test_series_query_processor_supports_locate_contract_case(self) -> None:
        processor = SeriesQueryProcessor(gateway=FakeLocateQueryGateway())

        result = processor.run(
            user_message="哪一节讲过 Nacos 3",
            series_id="series-1",
            series_title="Series 1",
            series_catalog={"series_id": "series-1", "videos": []},
            memory_messages=[],
        )

        self.assertEqual(result.filters, {"series_id": "series-1"})
        self.assertIn("Nacos 3", result.normalized_query)

    def test_series_answer_synthesizer_returns_structured_payload(self) -> None:
        synthesizer = SeriesAnswerSynthesizer(gateway=FakeAnswerGateway())
        debug_trace: dict[str, object] = {}

        payload = synthesizer.run(
            user_message="这个系列讲了啥",
            query_understanding=SeriesQueryUnderstanding(
                normalized_query="这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
                subqueries=["这个系列主要讲哪些主题"],
                filters={"series_id": "series-1"},
            ),
            retrieval_hits=[
                RetrievalHit(
                    evidence_id="e1",
                    doc_id="series:1:video:video-1:summary_global",
                    series_id="series-1",
                    video_id="video-1",
                    source_type="summary_global",
                    source_family="summary",
                    title="Video 1",
                    chapter_title=None,
                    start_seconds=None,
                    end_seconds=None,
                    score=0.9,
                    text="这是一个视频摘要",
                )
            ],
            series_catalog={
                "series_id": "series-1",
                "series_title": "Series 1",
                "videos": [
                    {"video_id": "video-1", "title": "Video 1", "processed": True},
                ],
            },
            debug_trace=debug_trace,
        )

        self.assertIsInstance(payload, SeriesAnswerPayload)
        self.assertEqual(payload.used_source_types, ["summary_global"])
        self.assertEqual(payload.citations, ["e1"])
        self.assertIn("answer_synthesis", debug_trace)
        user_prompt = debug_trace["answer_synthesis"]["input"]["messages"][1]["content"]
        self.assertIn("series_catalog:", user_prompt)
        self.assertIn('"video_count": 1', user_prompt)

    def test_series_answer_payload_rejects_inline_citation_as_json_array(self) -> None:
        raw_text = "这个系列主要讲多智能体、环境准备和框架导读 [1][2][6]"

        with self.assertRaisesRegex(ValueError, "JSON 对象"):
            validate_json_response(raw_text=raw_text, response_model=SeriesAnswerPayload)

    def test_series_answer_payload_schema_uses_evidence_id_strings(self) -> None:
        schema = SeriesAnswerPayload.model_json_schema()

        citation_items_schema = schema["properties"]["citations"]["items"]

        self.assertEqual(citation_items_schema["type"], "string")

    def test_series_graph_uses_new_understand_retrieve_answer_path(self) -> None:
        retriever = FakeSeriesRetriever()
        graph = build_agent_graph(
            series_query_processor=FakeSeriesQueryProcessor(),
            retrieval_service=retriever,
            series_answer_synthesizer=FakeSeriesAnswerSynthesizer(),
        )

        result = graph.invoke(
            {
                "session_id": "series|series-1|series-home",
                "scope_type": "series",
                "series_id": "series-1",
                "video_id": "",
                "user_message": "这个系列讲了啥",
                "memory_messages": [],
            }
        )

        self.assertEqual(result["answer_payload"]["answer"], "这个系列主要讲多智能体和框架导读。")
        self.assertEqual(result["assistant_message"], "这个系列主要讲多智能体和框架导读。")
        self.assertIn("query_understanding", result)
        self.assertIn("retrieval_results", result)
        self.assertEqual(retriever.last_search_kwargs["max_hits"], 5)
        self.assertNotIn("query_plan", result)
        self.assertNotIn("current_subplan", result)

    def test_series_retrieval_uses_subqueries_and_diversifies_by_video(self) -> None:
        retriever = QueryAwareSeriesRetriever()
        graph = build_agent_graph(
            series_query_processor=FakeSeriesQueryProcessor(),
            retrieval_service=retriever,
            series_answer_synthesizer=FakeSeriesAnswerSynthesizer(),
        )

        result = graph.invoke(
            {
                "session_id": "series|series-1|series-home",
                "scope_type": "series",
                "series_id": "series-1",
                "video_id": "",
                "user_message": "这个系列讲了啥",
                "memory_messages": [],
            }
        )

        self.assertEqual(
            [call["query"] for call in retriever.search_calls],
            [
                "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
                "这个系列主要讲哪些主题",
            ],
        )
        self.assertEqual(
            [item["video_id"] for item in result["retrieval_results"]],
            ["video-1", "video-2", "video-1"],
        )
        self.assertEqual(
            [item["evidence_id"] for item in result["retrieval_results"]],
            ["e1", "e3", "e2"],
        )

    def test_series_graph_passes_catalog_to_answer_without_polluting_retrieval_hits(self) -> None:
        retriever = FakeSeriesRetriever()
        synthesizer = FakeSeriesAnswerSynthesizer()
        graph = build_agent_graph(
            series_query_processor=FakeSeriesQueryProcessor(),
            retrieval_service=retriever,
            series_answer_synthesizer=synthesizer,
            workspace=FakeCatalogWorkspace(),
        )

        result = graph.invoke(
            {
                "session_id": "series|series-1|series-home",
                "scope_type": "series",
                "series_id": "series-1",
                "video_id": "",
                "user_message": "这个系列总共有几个视频",
                "memory_messages": [],
            }
        )

        self.assertEqual(len(result["series_catalog"]["videos"]), 5)
        self.assertEqual(len(result["retrieval_results"]), 1)
        self.assertEqual(result["retrieval_results"][0]["source_type"], "summary_global")
        self.assertEqual(len(synthesizer.last_series_catalog["videos"]), 5)

    def test_series_graph_builds_evidence_items_without_web_when_search_is_disabled(self) -> None:
        web_search = FakeWebSearchGateway()
        synthesizer = FakeSeriesAnswerSynthesizer()
        graph = build_agent_graph(
            series_query_processor=FakeSeriesQueryProcessor(),
            retrieval_service=FakeSeriesRetriever(),
            series_answer_synthesizer=synthesizer,
            web_search_gateway=web_search,
            web_search_settings=FakeWebSearchSettings(enabled=False),
        )

        result = graph.invoke(
            {
                "session_id": "series|series-1|series-home",
                "scope_type": "series",
                "series_id": "series-1",
                "video_id": "",
                "user_message": "这个系列讲了啥",
                "memory_messages": [],
            }
        )

        self.assertFalse(web_search.called)
        self.assertEqual(len(result["retrieval_results"]), 1)
        self.assertEqual(result["evidence_items"][0]["source_family"], "summary")
        self.assertEqual(synthesizer.last_evidence_items[0]["source_family"], "summary")

    def test_series_graph_adds_web_evidence_when_local_retrieval_is_empty_and_search_enabled(self) -> None:
        web_search = FakeWebSearchGateway()
        synthesizer = FakeSeriesAnswerSynthesizer()
        graph = build_agent_graph(
            series_query_processor=FakeSeriesQueryProcessor(),
            retrieval_service=EmptySeriesRetriever(),
            series_answer_synthesizer=synthesizer,
            web_search_gateway=web_search,
            web_search_settings=FakeWebSearchSettings(enabled=True),
        )

        result = graph.invoke(
            {
                "session_id": "series|series-1|series-home",
                "scope_type": "series",
                "series_id": "series-1",
                "video_id": "",
                "user_message": "这个系列外的最新情况是什么",
                "memory_messages": [],
            }
        )

        self.assertTrue(web_search.called)
        self.assertEqual(result["web_search_results"][0]["url"], "https://example.com/article")
        self.assertEqual(result["evidence_items"][0]["source_family"], "web")
        self.assertEqual(result["evidence_items"][0]["source_type"], "web_search")
        self.assertEqual(synthesizer.last_evidence_items[0]["source_family"], "web")

    def test_series_graph_wraps_web_search_timeout_with_clear_error_context(self) -> None:
        graph = build_agent_graph(
            series_query_processor=FakeSeriesQueryProcessor(),
            retrieval_service=EmptySeriesRetriever(),
            series_answer_synthesizer=FakeSeriesAnswerSynthesizer(),
            web_search_gateway=TimeoutWebSearchGateway(),
            web_search_settings=FakeWebSearchSettings(enabled=True),
        )

        with self.assertRaisesRegex(RuntimeError, "联网搜索失败：Request timed out"):
            graph.invoke(
                {
                    "session_id": "series|series-1|series-home",
                    "scope_type": "series",
                    "series_id": "series-1",
                    "video_id": "",
                    "user_message": "联网查一下",
                    "memory_messages": [],
                }
            )

    def test_turn_builder_uses_new_reason_contract(self) -> None:
        builder = AgentGraphTurnBuilder()

        turn = builder.build(
            context=AgentContext(
                session_id="series|series-1|series-home",
                scope_type=ScopeType.SERIES.value,
                series_id="series-1",
            ),
            result={
                "assistant_message": "回答",
                "answer": "回答",
                "query_understanding": {
                    "normalized_query": "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
                    "subqueries": [],
                    "filters": {"series_id": "series-1"},
                },
                "retrieval_results": [],
                "tool_results": [],
            },
        )

        self.assertEqual(turn.plan.reason, "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？")

    def test_service_run_turn_collects_debug_trace_without_graph_state_injection(self) -> None:
        debug_trace: dict[str, object] = {}
        service = AgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-1|series-home",
                    scope_type=ScopeType.SERIES.value,
                    series_id="series-1",
                )
            ),
            graph=build_agent_graph(
                series_query_processor=FakeSeriesQueryProcessor(),
                retrieval_service=FakeSeriesRetriever(),
                series_answer_synthesizer=FakeSeriesAnswerSynthesizer(),
            ),
            session_store=FakeSessionStore(),
        )

        turn = service.run_turn(
            session_id="series|series-1|series-home",
            user_message="这个系列讲了啥",
            debug_trace=debug_trace,
        )

        self.assertTrue(turn.assistant_message)
        self.assertIn("graph_input", debug_trace)
        self.assertIn("series_query_processor", debug_trace)
        self.assertIn("retrieval_request", debug_trace)
        self.assertIn("retrieval_response", debug_trace)
        self.assertIn("answer_synthesis", debug_trace)

    def test_session_recorder_does_not_persist_selected_videos(self) -> None:
        store = FakeSessionStore()
        recorder = AgentGraphSessionRecorder(session_store=store)

        recorder.persist_turn(
            session_id="series|series-1|series-home",
            context=AgentContext(
                session_id="series|series-1|series-home",
                scope_type=ScopeType.SERIES.value,
                series_id="series-1",
            ),
            user_message="这个系列讲了啥",
            result={
                "assistant_message": "回答",
            },
            turn_result=builder_turn_result("回答"),
        )

        self.assertNotIn("selected_videos", store.last_append)

    def test_file_session_store_persists_only_context_and_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileAgentSessionStore(Path(temp_dir))

            store.append_turn(
                session_id="series|series-1|series-home",
                memory_key="series|series-1|series-home",
                context=AgentContext(
                    session_id="series|series-1|series-home",
                    scope_type=ScopeType.SERIES.value,
                    series_id="series-1",
                    selected_tool="series-home",
                ),
                messages=[
                    AgentChatMessage(role="user", content="这个系列讲什么？"),
                    AgentChatMessage(role="assistant", content="讲 RAG。"),
                ],
            )

            [snapshot_path] = Path(temp_dir).glob("*.json")
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

        self.assertEqual(set(payload), {"session_id", "memory_key", "context", "messages", "updated_at"})
        self.assertNotIn("dialog_history", payload["context"])
        self.assertNotIn("history_summary", payload["context"])
        self.assertNotIn("evidence_history", payload["context"])
        self.assertNotIn("evidence_entries", payload)

    def test_graph_input_builder_uses_persisted_messages_as_memory_messages(self) -> None:
        session_id = "video|series-1|video-1|overview"
        store = FakeSnapshotStore(
            AgentSessionSnapshot(
                session_id=session_id,
                memory_key=session_id,
                context=AgentContext(
                    session_id=session_id,
                    scope_type=ScopeType.VIDEO.value,
                    series_id="series-1",
                    video_id="video-1",
                    selected_tool="overview",
                ),
                messages=[
                    AgentSessionMessageEntry(role="system", content="更早对话摘要：用户关注 embedding。", created_at="t1"),
                    AgentSessionMessageEntry(role="user", content="刚才那段是什么？", created_at="t2"),
                    AgentSessionMessageEntry(role="assistant", content="是在讲向量检索。", created_at="t2"),
                ],
                updated_at="t2",
            )
        )
        builder = AgentGraphInputBuilder(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id=session_id,
                    scope_type=ScopeType.VIDEO.value,
                    series_id="series-1",
                    video_id="video-1",
                    selected_tool="overview",
                )
            ),
            session_store=store,
        )

        bundle = builder.build(
            session_id=session_id,
            user_message="帮我定位",
        )

        self.assertEqual(
            bundle.payload["memory_messages"],
            [
                {"role": "system", "content": "更早对话摘要：用户关注 embedding。"},
                {"role": "user", "content": "刚才那段是什么？"},
                {"role": "assistant", "content": "是在讲向量检索。"},
            ],
        )
        self.assertNotIn("dialog_history", bundle.payload)
        self.assertNotIn("history_messages", bundle.payload)
        self.assertNotIn("history_summary", bundle.payload)
        self.assertNotIn("evidence_history", bundle.payload)

    def test_session_recorder_replaces_messages_with_compacted_summary(self) -> None:
        session_id = "series|series-1|series-home"
        store = FakeSnapshotStore(
            AgentSessionSnapshot(
                session_id=session_id,
                memory_key=session_id,
                context=AgentContext(
                    session_id=session_id,
                    scope_type=ScopeType.SERIES.value,
                    series_id="series-1",
                ),
                messages=[
                    AgentSessionMessageEntry(role="user", content="旧问题", created_at="t1"),
                    AgentSessionMessageEntry(role="assistant", content="旧回答", created_at="t1"),
                ],
                updated_at="t1",
            )
        )
        recorder = AgentGraphSessionRecorder(
            session_store=store,
            memory_compactor=FakeMessageCompactor(),
        )

        recorder.persist_turn(
            session_id=session_id,
            context=AgentContext(
                session_id=session_id,
                scope_type=ScopeType.SERIES.value,
                series_id="series-1",
            ),
            user_message="新问题",
            result={"assistant_message": "新回答"},
            turn_result=builder_turn_result("新回答"),
        )

        self.assertEqual(
            store.last_append["messages"],
            [
                AgentChatMessage(role="system", content="更早对话摘要：旧问题、旧回答、新问题、新回答。"),
            ],
        )
        self.assertNotIn("tool_results", store.last_append)

    def test_session_recorder_persists_assistant_citations_with_message(self) -> None:
        session_id = "series|series-1|series-home"
        store = FakeSnapshotStore(None)
        recorder = AgentGraphSessionRecorder(session_store=store)

        recorder.persist_turn(
            session_id=session_id,
            context=AgentContext(
                session_id=session_id,
                scope_type=ScopeType.SERIES.value,
                series_id="series-1",
            ),
            user_message="这个结论来自哪里？",
            result={"assistant_message": "来自课程摘要。[1]"},
            turn_result=builder_turn_result(
                "来自课程摘要。[1]",
                citations_payload=[
                    {
                        "id": "1",
                        "label": "Video 1",
                        "source_type": "summary",
                        "search_scope": "summary",
                        "slots": [
                            {
                                "slot": 1,
                                "target_type": "summary",
                                "video_id": "video-1",
                                "video_title": "Video 1",
                                "text": "课程摘要证据",
                            }
                        ],
                    }
                ],
            ),
        )

        assistant_message = store.last_append["messages"][-1]
        self.assertEqual(assistant_message.role, "assistant")
        self.assertEqual(assistant_message.citations[0].id, "1")

    def test_agent_chat_response_keeps_external_shape_without_internal_fields(self) -> None:
        response = AgentChatResponse.from_result(
            builder_turn_result(
                "回答",
                citations_payload=[
                    {
                        "id": "1",
                        "label": "Series 1 总览",
                        "source_type": "summary_global",
                        "search_scope": "summary",
                        "slots": [
                            {
                                "slot": 1,
                                "target_type": "summary",
                                "video_id": "video-1",
                                "video_title": "Video 1",
                                "text": "摘要",
                            }
                        ],
                    }
                ],
            )
        )

        dumped = response.model_dump(mode="json")
        self.assertIn("assistant_message", dumped)
        self.assertIn("scope_type", dumped)
        self.assertIn("reason", dumped)
        self.assertIn("tool_results", dumped)
        self.assertIn("citations", dumped)
        self.assertNotIn("doc_id", json_dumps(dumped))
        self.assertNotIn("score", json_dumps(dumped))

    def test_turn_builder_includes_web_search_citations_with_url(self) -> None:
        builder = AgentGraphTurnBuilder()

        turn = builder.build(
            context=AgentContext(
                session_id="series|series-1|series-home",
                scope_type=ScopeType.SERIES.value,
                series_id="series-1",
            ),
            result={
                "assistant_message": "联网补充见 [1]",
                "answer": "联网补充见 [1]",
                "query_understanding": {
                    "normalized_query": "联网查一下",
                    "subqueries": [],
                    "filters": {"series_id": "series-1"},
                },
                "evidence_items": [
                    {
                        "evidence_id": "web-1",
                        "source_type": "web_search",
                        "source_family": "web",
                        "title": "联网资料",
                        "url": "https://example.com/article",
                        "text": "联网搜索摘要",
                    }
                ],
                "tool_results": [],
            },
        )

        response = AgentChatResponse.from_result(turn)
        dumped = response.model_dump(mode="json")

        self.assertEqual(dumped["citations"][0]["source_type"], "web")
        self.assertEqual(dumped["citations"][0]["search_scope"], "web")
        self.assertEqual(dumped["citations"][0]["slots"][0]["target_type"], "web")
        self.assertEqual(dumped["citations"][0]["slots"][0]["url"], "https://example.com/article")

    def test_turn_builder_omits_invalid_web_search_citation_without_url(self) -> None:
        builder = AgentGraphTurnBuilder()

        turn = builder.build(
            context=AgentContext(
                session_id="series|series-1|series-home",
                scope_type=ScopeType.SERIES.value,
                series_id="series-1",
            ),
            result={
                "assistant_message": "回答",
                "answer": "回答",
                "query_understanding": {
                    "normalized_query": "联网查一下",
                    "subqueries": [],
                    "filters": {"series_id": "series-1"},
                },
                "evidence_items": [
                    {
                        "evidence_id": "web-1",
                        "source_type": "web_search",
                        "source_family": "web",
                        "title": "缺少 URL",
                        "text": "联网搜索摘要",
                    }
                ],
                "tool_results": [],
            },
        )

        self.assertEqual(turn.citations, [])

    def test_video_scope_injects_summary_and_full_transcript_without_old_planning(self) -> None:
        workspace = FakeVideoWorkspace(
            transcript_text="第一句介绍 LLMOps。第二句说明它管理模型上线和监控。",
        )
        answer = FakeVideoAnswerProgram()
        graph = build_agent_graph(
            retrieval_service=ExplodingRetriever(),
            answer_program=answer,
            workspace=workspace,
            context_window_tokens=10_000,
            reserved_output_tokens=100,
        )

        result = graph.invoke(video_graph_input("LLMOps 是啥"))

        self.assertEqual(result["assistant_message"], "video answer")
        self.assertNotIn("query_plan", result)
        self.assertNotIn("current_subplan", result)
        source_types = [item["source_type"] for item in answer.last_retrieval_results]
        self.assertEqual(source_types, ["summary_global", "transcript_full"])
        self.assertIn("第一句介绍 LLMOps", answer.last_retrieval_results[1]["text"])
        self.assertEqual([item["source_type"] for item in answer.last_evidence_items], ["summary_global", "transcript_full"])

    def test_video_graph_adds_web_evidence_when_user_explicitly_requests_search(self) -> None:
        workspace = FakeVideoWorkspace(transcript_text="第一句介绍 LLMOps。")
        web_search = FakeWebSearchGateway()
        answer = FakeVideoAnswerProgram()
        graph = build_agent_graph(
            retrieval_service=ExplodingRetriever(),
            answer_program=answer,
            workspace=workspace,
            web_search_gateway=web_search,
            web_search_settings=FakeWebSearchSettings(enabled=True),
            context_window_tokens=10_000,
            reserved_output_tokens=100,
        )

        result = graph.invoke(video_graph_input("联网查一下 LLMOps 最新情况"))

        self.assertEqual(result["assistant_message"], "video answer")
        self.assertTrue(web_search.called)
        self.assertEqual(answer.last_evidence_items[-1]["source_family"], "web")
        self.assertEqual(answer.last_evidence_items[-1]["url"], "https://example.com/article")

    def test_video_scope_uses_summary_and_transcript_rag_when_full_transcript_exceeds_context(self) -> None:
        workspace = FakeVideoWorkspace(transcript_text="超长转录 " * 200)
        retriever = FakeTranscriptRetriever()
        answer = FakeVideoAnswerProgram()
        graph = build_agent_graph(
            retrieval_service=retriever,
            answer_program=answer,
            workspace=workspace,
            context_window_tokens=220,
            reserved_output_tokens=100,
        )

        result = graph.invoke(video_graph_input("LLMOps 是啥"))

        self.assertEqual(result["assistant_message"], "video answer")
        self.assertNotIn("query_plan", result)
        self.assertEqual(retriever.last_search_kwargs["target_source"], "transcript")
        self.assertEqual(retriever.last_search_kwargs["scope_type"], "video")
        source_types = [item["source_type"] for item in answer.last_retrieval_results]
        self.assertEqual(source_types, ["summary_global", "transcript_chunk"])

    def test_video_scope_executes_save_note_action_from_context_evidence(self) -> None:
        workspace = FakeVideoWorkspace(
            transcript_text="这里说明 RAG 先读取视频概况，再按问题检索转写片段。",
        )
        planner = FakeVideoActionPlanner(
            [
                SaveNoteCall(
                    note_title="RAG 检索流程",
                    note_content="先读取视频概况，再按问题检索转写片段。",
                )
            ]
        )
        answer = FakeVideoAnswerProgram()
        graph = build_agent_graph(
            retrieval_service=ExplodingRetriever(),
            answer_program=answer,
            workspace=workspace,
            video_action_planner=planner,
            tool_executor=RegistryAgentToolExecutor(
                registry={ToolName.SAVE_NOTE: execute_save_note}
            ),
            context_window_tokens=10_000,
            reserved_output_tokens=100,
        )

        result = graph.invoke(video_graph_input("帮我记一下 RAG 检索流程"))

        self.assertEqual(planner.last_retrieval_results[0]["source_type"], "summary_global")
        self.assertEqual(result["tool_results"][0]["tool_name"], "save_note")
        self.assertEqual(result["tool_results"][0]["payload"]["action"], "save_note")
        self.assertEqual(result["tool_results"][0]["payload"]["note_title"], "RAG 检索流程")
        self.assertNotEqual(result["tool_results"][0]["tool_name"], "get_video_transcript")
        self.assertEqual(answer.last_meta_state["action_summary"], "video action completed")

    def test_video_scope_executes_video_seek_action_from_transcript_hit(self) -> None:
        workspace = FakeVideoWorkspace(transcript_text="超长转录 " * 200)
        retriever = FakeTranscriptRetriever()
        planner = FakeVideoActionPlanner(
            [
                VideoSeekCall(
                    seek_seconds=12.0,
                    match_end_seconds=18.0,
                    matched_text="RAG 命中的转录片段",
                    query="RAG",
                )
            ]
        )
        graph = build_agent_graph(
            retrieval_service=retriever,
            answer_program=FakeVideoAnswerProgram(),
            workspace=workspace,
            video_action_planner=planner,
            tool_executor=RegistryAgentToolExecutor(
                registry={ToolName.VIDEO_SEEK: execute_video_seek}
            ),
            context_window_tokens=220,
            reserved_output_tokens=100,
        )

        result = graph.invoke(video_graph_input("跳到 RAG 那段"))

        self.assertEqual(planner.last_retrieval_results[-1]["source_type"], "transcript_chunk")
        self.assertEqual(result["tool_results"][0]["tool_name"], "video_seek")
        self.assertEqual(result["tool_results"][0]["payload"]["seek_seconds"], 12.0)
        self.assertEqual(result["tool_results"][0]["payload"]["matched_text"], "RAG 命中的转录片段")

    def test_video_scope_executes_open_notes_action(self) -> None:
        workspace = FakeVideoWorkspace(transcript_text="普通转写")
        graph = build_agent_graph(
            retrieval_service=ExplodingRetriever(),
            answer_program=FakeVideoAnswerProgram(),
            workspace=workspace,
            video_action_planner=FakeVideoActionPlanner([OpenNotesCall()]),
            tool_executor=RegistryAgentToolExecutor(
                registry={ToolName.OPEN_NOTES: execute_open_notes}
            ),
            context_window_tokens=10_000,
            reserved_output_tokens=100,
        )

        result = graph.invoke(video_graph_input("打开笔记"))

        self.assertEqual(result["tool_results"][0]["tool_name"], "open_notes")
        self.assertEqual(result["tool_results"][0]["payload"]["selected_tool"], "notes")

    def test_video_action_planner_uses_tool_schema_contracts(self) -> None:
        planner = VideoActionPlanner(gateway=FakeVideoActionGateway())

        plan = planner.run(
            user_message="帮我记一下 RAG 检索流程",
            retrieval_results=[
                {
                    "source_type": "transcript_chunk",
                    "source_family": "transcript",
                    "title": "Video 1",
                    "start_seconds": 12.0,
                    "end_seconds": 18.0,
                    "text": "RAG 先读取视频概况，再按问题检索转写片段。",
                    "snippet": "RAG 先读取视频概况，再按问题检索转写片段。",
                }
            ],
        )

        self.assertIsInstance(plan.tool_calls[0], SaveNoteCall)
        self.assertEqual(plan.tool_calls[0].note_title, "RAG 检索流程")
        self.assertEqual(plan.tool_calls[0].note_content, "先读取视频概况，再按问题检索转写片段。")

    def test_video_action_planner_payload_schema_avoids_openai_unsupported_one_of(self) -> None:
        schema = VideoActionPlannerPayload.model_json_schema()
        serialized_schema = json.dumps(schema)

        self.assertNotIn('"oneOf"', serialized_schema)
        self.assertEqual(
            schema["$defs"]["PlannedVideoToolCall"]["properties"]["tool_name"]["enum"],
            ["open_notes", "save_note", "video_seek"],
        )

    def test_save_note_contract_prefers_markdown_content_without_fixed_template(self) -> None:
        self.assertIn("Markdown", VIDEO_ACTION_PLANNER_SYSTEM_PROMPT)
        self.assertIn("按内容复杂度", VIDEO_ACTION_PLANNER_SYSTEM_PROMPT)
        self.assertIn("支持 Markdown 的笔记正文", SAVE_NOTE_TOOL.arguments["note_content"])
        self.assertNotIn("视频核心", VIDEO_ACTION_PLANNER_SYSTEM_PROMPT)

    def test_stream_with_context_streams_deferred_series_answer_from_gateway(self) -> None:
        synthesizer = FakeDeferredSeriesAnswerSynthesizer()
        stream_gateway = FakeAnswerStreamGateway(["**结论：**", "真实流式回答。[1]"])
        graph = build_agent_graph(
            series_query_processor=FakeSeriesQueryProcessor(),
            retrieval_service=FakeSeriesRetriever(),
            series_answer_synthesizer=synthesizer,
        )
        session_store = FakeSessionStore()
        service = AgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-1|series-home",
                    scope_type="series",
                    series_id="series-1",
                )
            ),
            graph=graph,
            session_store=session_store,
            answer_stream_gateway=stream_gateway,
        )

        events = list(
            service.stream_with_context(
                session_id="series|series-1|series-home",
                user_message="这个系列讲了啥",
            )
        )

        deltas = [
            event.payload["delta"]
            for event in events
            if event.type == "answer_delta"
        ]
        completed = next(event for event in events if event.type == "answer_completed")

        self.assertEqual(deltas, ["**结论：**", "真实流式回答。[1]"])
        self.assertFalse(synthesizer.run_called)
        self.assertEqual(completed.payload["message"], "**结论：**真实流式回答。[1]")
        self.assertEqual(len(completed.payload["citations"]), 1)
        self.assertEqual(completed.payload["citations"][0]["id"], "1")
        self.assertEqual(stream_gateway.messages[0].role, "system")
        persisted_messages = session_store.last_append["messages"]
        self.assertEqual(persisted_messages[-1].content, "**结论：**真实流式回答。[1]")

    def test_inline_citation_parser_rejects_unknown_source_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "未知引用编号"):
            extract_inline_source_numbers(
                "这个结论来自不存在的证据。[99]",
                [{"evidence_id": "e1"}],
            )

    def test_inline_citation_parser_ignores_markdown_link_labels(self) -> None:
        numbers = extract_inline_source_numbers(
            "可以参考 [React](https://example.com)，课程证据在这里。[1]",
            [{"evidence_id": "e1"}],
        )

        self.assertEqual(numbers, [1])

    def test_inline_citation_resolution_normalizes_and_removes_bad_markers(self) -> None:
        resolution = resolve_inline_citations(
            "课程证据 A。[ 1] 模型打错的标记。[ee2][local-1] 普通链接 [React](https://example.com)",
            [{"evidence_id": "e1"}],
        )

        self.assertEqual(resolution.used_source_numbers, [1])
        self.assertEqual(resolution.used_evidence_ids, ["e1"])
        self.assertIn("[1]", resolution.answer_text)
        self.assertNotIn("[ee2]", resolution.answer_text)
        self.assertNotIn("[local-1]", resolution.answer_text)
        self.assertIn("[React](https://example.com)", resolution.answer_text)

    def test_citation_builder_uses_source_number_as_citation_id(self) -> None:
        turn = AgentGraphTurnBuilder().build(
            context=AgentContext(session_id="s1", scope_type="video", series_id="series-1", video_id="video-1"),
            result={
                "assistant_message": "answer [2]",
                "answer": "answer [2]",
                "used_evidence_ids": ["local-2"],
                "evidence_items": [
                    {
                        "evidence_id": "local-2",
                        "source_number": 2,
                        "series_id": "series-1",
                        "video_id": "video-1",
                        "title": "Video 1",
                        "source_type": "summary_global",
                        "source_family": "summary",
                        "text": "summary",
                        "snippet": "summary",
                    }
                ],
            },
        )

        self.assertEqual(turn.citations[0].id, "2")

    def test_citation_builder_preserves_original_source_number_when_filtering_used_evidence(self) -> None:
        turn = AgentGraphTurnBuilder().build(
            context=AgentContext(session_id="s1", scope_type="series", series_id="series-1", video_id=""),
            result={
                "assistant_message": "answer [4]",
                "answer": "answer [4]",
                "used_evidence_ids": ["local-4"],
                "evidence_items": [
                    {
                        "evidence_id": "local-1",
                        "series_id": "series-1",
                        "video_id": "video-1",
                        "title": "Video 1",
                        "source_type": "summary_global",
                        "text": "one",
                        "snippet": "one",
                    },
                    {
                        "evidence_id": "local-2",
                        "series_id": "series-1",
                        "video_id": "video-2",
                        "title": "Video 2",
                        "source_type": "summary_global",
                        "text": "two",
                        "snippet": "two",
                    },
                    {
                        "evidence_id": "local-3",
                        "series_id": "series-1",
                        "video_id": "video-3",
                        "title": "Video 3",
                        "source_type": "summary_global",
                        "text": "three",
                        "snippet": "three",
                    },
                    {
                        "evidence_id": "local-4",
                        "series_id": "series-1",
                        "video_id": "video-4",
                        "title": "Video 4",
                        "source_type": "summary_global",
                        "text": "four",
                        "snippet": "four",
                    },
                ],
            },
        )

        self.assertEqual(len(turn.citations), 1)
        self.assertEqual(turn.citations[0].id, "4")

    def test_citation_builder_includes_full_transcript_citation(self) -> None:
        turn = AgentGraphTurnBuilder().build(
            context=AgentContext(session_id="s1", scope_type="video", series_id="series-1", video_id="video-1"),
            result={
                "assistant_message": "answer [2]",
                "answer": "answer [2]",
                "used_evidence_ids": ["local-2"],
                "evidence_items": [
                    {
                        "evidence_id": "local-2",
                        "source_number": 2,
                        "series_id": "series-1",
                        "video_id": "video-1",
                        "title": "Video 1",
                        "source_type": "transcript_full",
                        "source_family": "transcript",
                        "start_seconds": 10.0,
                        "end_seconds": 70.0,
                        "text": "完整字幕内容",
                        "snippet": "完整字幕内容",
                    }
                ],
            },
        )

        self.assertEqual(len(turn.citations), 1)
        citation = turn.citations[0]
        self.assertEqual(citation.id, "2")
        self.assertEqual(citation.source_type, "transcript")
        self.assertEqual(citation.search_scope, "transcript")
        self.assertEqual(citation.slots[0].target_type, "video")
        self.assertEqual(citation.slots[0].start_seconds, 10.0)
        self.assertEqual(citation.slots[0].end_seconds, 70.0)
        self.assertEqual(citation.slots[1].target_type, "transcript")
        self.assertEqual(citation.slots[1].text, "完整字幕内容")


class FakeQueryGateway:
    def create_structured_completion(self, messages, response_model):
        del messages
        return response_model(
            normalized_query="这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
            subqueries=["这个系列主要讲哪些主题", "这个系列的学习顺序是什么"],
            filters={"series_id": "series-1"},
        )


class FakeAnswerGateway:
    def create_structured_completion(self, messages, response_model):
        self.messages = messages
        return response_model(
            answer="这个系列主要讲多智能体、环境准备和框架导读。",
            citations=["e1"],
            used_source_types=["summary_global"],
        )


class FakeConceptQueryGateway:
    def create_structured_completion(self, messages, response_model):
        del messages
        return response_model(
            normalized_query="Copilot 模式的定义、作用，以及它在本系列中的上下文",
            subqueries=["Copilot 模式是什么", "Copilot 模式和 Agent 模式有什么区别"],
            filters={"series_id": "series-1"},
        )


class FakeLocateQueryGateway:
    def create_structured_completion(self, messages, response_model):
        del messages
        return response_model(
            normalized_query="定位系列中提到 Nacos 3 的视频、章节和大致位置",
            subqueries=["Nacos 3", "安装 Nacos 3", "Nacos 3 端口"],
            filters={"series_id": "series-1"},
        )


class ExplodingRetriever:
    def search(self, **kwargs):
        del kwargs
        raise AssertionError("small video transcript should be injected without RAG")


class FakeTranscriptRetriever:
    def __init__(self) -> None:
        self.last_search_kwargs: dict[str, object] = {}

    def search(self, **kwargs):
        self.last_search_kwargs = dict(kwargs)
        return {
            "hits": [
                {
                    "series_id": "series-1",
                    "video_id": "video-1",
                    "title": "Video 1",
                    "source_type": "transcript_chunk",
                    "source_family": "transcript",
                    "start_seconds": 0.0,
                    "end_seconds": 6.0,
                    "text": "RAG 命中的转录片段",
                    "snippet": "RAG 命中的转录片段",
                }
            ]
        }


class EmptySeriesRetriever:
    def __init__(self) -> None:
        self.last_search_kwargs: dict[str, object] = {}

    def search(self, **kwargs):
        self.last_search_kwargs = dict(kwargs)
        return {"hits": []}


class FakeWebSearchSettings:
    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled
        self.provider = "litellm"
        self.mode = "native"
        self.search_context_size = "medium"
        self.max_results = 3
        self.timeout_seconds = 5


class FakeWebSearchGateway:
    def __init__(self) -> None:
        self.called = False
        self.last_query = ""
        self.last_max_results = 0
        self.last_timeout_seconds = 0

    def search(self, query: str, *, max_results: int, timeout_seconds: int):
        self.called = True
        self.last_query = query
        self.last_max_results = max_results
        self.last_timeout_seconds = timeout_seconds
        return [
            {
                "title": "联网资料",
                "url": "https://example.com/article",
                "text": "这是联网搜索摘要",
                "snippet": "这是联网搜索摘要",
                "published_at": "2026-05-08",
            }
        ]


class TimeoutWebSearchGateway:
    def search(self, query: str, *, max_results: int, timeout_seconds: int):
        del query, max_results, timeout_seconds
        raise TimeoutError("Request timed out")


class FakeVideoAnswerProgram:
    def __init__(self) -> None:
        self.last_retrieval_results: list[dict[str, object]] = []
        self.last_evidence_items: list[dict[str, object]] = []
        self.last_meta_state: dict[str, object] = {}

    def run(self, **kwargs):
        self.last_retrieval_results = list(kwargs.get("retrieval_results", []))
        self.last_evidence_items = list(kwargs.get("evidence_items", self.last_retrieval_results))
        self.last_meta_state = dict(kwargs.get("meta_state", {}))
        return "video answer"


class FakeVideoActionPlan:
    def __init__(self, tool_calls) -> None:
        self.tool_calls = tool_calls
        self.action_summary = "video action completed"


class FakeVideoActionPlanner:
    def __init__(self, tool_calls) -> None:
        self._tool_calls = tool_calls
        self.last_retrieval_results: list[dict[str, object]] = []

    def run(self, **kwargs):
        self.last_retrieval_results = list(kwargs.get("retrieval_results", []))
        return FakeVideoActionPlan(self._tool_calls)


class FakeVideoActionGateway:
    def create_structured_completion(self, messages, response_model):
        self.messages = messages
        self.response_model = response_model
        self.assert_response_model()
        return VideoActionPlannerPayload(
            tool_calls=[
                {
                    "tool_name": "save_note",
                    "note_title": "RAG 检索流程",
                    "note_content": "先读取视频概况，再按问题检索转写片段。",
                }
            ],
            action_summary="已保存笔记。",
        )

    def assert_response_model(self) -> None:
        if self.response_model is not VideoActionPlannerPayload:
            raise AssertionError("video action planner must request structured output")


class FakeVideoWorkspace:
    def __init__(self, *, transcript_text: str) -> None:
        self._transcript_text = transcript_text

    def get_video_summary(self, series_id: str, video_id: str):
        return VideoSummaryDTO(
            series_id=series_id,
            video_id=video_id,
            title="Video 1",
            summary={
                "one_sentence_summary": "这个视频介绍 LLMOps。",
                "core_problem": "如何管理 LLM 应用生命周期。",
                "key_takeaways": ["监控", "评估", "部署"],
            },
        )

    def get_video_transcript(self, series_id: str, video_id: str):
        return VideoTranscriptDTO(
            series_id=series_id,
            video_id=video_id,
            title="Video 1",
            duration_seconds=10.0,
            segments=[
                TranscriptSegmentDTO(
                    start_seconds=0.0,
                    end_seconds=10.0,
                    text=self._transcript_text,
                )
            ],
        )


class FakeSeriesQueryProcessor:
    def run(self, **kwargs):
        debug_trace = kwargs.get("debug_trace")
        result = SeriesQueryUnderstanding(
            normalized_query="这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
            subqueries=["这个系列主要讲哪些主题"],
            filters={"series_id": "series-1"},
        )
        if isinstance(debug_trace, dict):
            debug_trace["series_query_processor"] = {
                "output": result.model_dump(mode="json"),
            }
        return result


class FakeSeriesRetriever:
    def __init__(self) -> None:
        self.last_search_kwargs: dict[str, object] = {}
        self.search_calls: list[dict[str, object]] = []

    def search(self, **kwargs):
        self.last_search_kwargs = dict(kwargs)
        self.search_calls.append(dict(kwargs))
        return {
            "hits": [
                {
                    "evidence_id": "e1",
                    "doc_id": "series:1:video:video-1:summary_global",
                    "series_id": "series-1",
                    "video_id": "video-1",
                    "source_type": "summary_global",
                    "source_family": "summary",
                    "title": "Video 1",
                    "chapter_title": None,
                    "start_seconds": None,
                    "end_seconds": None,
                    "score": 0.91,
                    "text": "这是一个视频摘要",
                    "snippet": "这是一个视频摘要",
                }
            ]
        }


def _series_hit(
    *,
    evidence_id: str,
    doc_id: str,
    video_id: str,
    source_type: str,
    score: float,
    text: str,
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "doc_id": doc_id,
        "series_id": "series-1",
        "video_id": video_id,
        "source_type": source_type,
        "source_family": "summary" if source_type.startswith("summary") else "transcript",
        "title": video_id,
        "chapter_title": None,
        "start_seconds": None,
        "end_seconds": None,
        "score": score,
        "text": text,
        "snippet": text,
    }


class QueryAwareSeriesRetriever:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []

    def search(self, **kwargs):
        self.search_calls.append(dict(kwargs))
        query = str(kwargs.get("query", "")).strip()
        if "学习顺序" in query:
            return {
                "hits": [
                    _series_hit(
                        evidence_id="e1",
                        doc_id="series:1:video:video-1:transcript:1",
                        video_id="video-1",
                        source_type="transcript_chunk",
                        score=0.99,
                        text="总纲和学习顺序",
                    ),
                    _series_hit(
                        evidence_id="e2",
                        doc_id="series:1:video:video-1:transcript:2",
                        video_id="video-1",
                        source_type="transcript_chunk",
                        score=0.98,
                        text="总纲重复片段",
                    ),
                ]
            }
        return {
            "hits": [
                _series_hit(
                    evidence_id="e3",
                    doc_id="series:1:video:video-2:summary_global",
                    video_id="video-2",
                    source_type="summary_global",
                    score=0.75,
                    text="第二节主题",
                )
            ]
        }


class FakeSeriesAnswerSynthesizer:
    def __init__(self) -> None:
        self.last_series_catalog: dict[str, object] = {}
        self.last_evidence_items: list[dict[str, object]] = []

    def run(self, **kwargs):
        debug_trace = kwargs.get("debug_trace")
        self.last_series_catalog = dict(kwargs.get("series_catalog", {}))
        self.last_evidence_items = list(kwargs.get("evidence_items", kwargs.get("retrieval_hits", [])))
        payload = SeriesAnswerPayload(
            answer="这个系列主要讲多智能体和框架导读。",
            citations=["e1"],
            used_source_types=["summary_global"],
        )
        if isinstance(debug_trace, dict):
            debug_trace["answer_synthesis"] = {
                "output": payload.model_dump(mode="json"),
            }
        return payload


class FakeDeferredSeriesAnswerSynthesizer:
    def __init__(self) -> None:
        self.run_called = False

    def run(self, **kwargs):
        del kwargs
        self.run_called = True
        raise AssertionError("streaming path must not call structured answer synthesis")

    def build_text_messages(self, **kwargs):
        del kwargs
        return [
            AgentChatMessage(role="system", content="只输出 Markdown 回答正文。"),
            AgentChatMessage(role="user", content="Source 1:\n这是一个视频摘要\n\nuser_message:\n这个系列讲了啥"),
        ]


class FakeAnswerStreamGateway:
    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas
        self.messages: list[AgentChatMessage] = []

    def create_text_completion_stream_with_metadata(self, messages):
        self.messages = list(messages)
        for delta in self._deltas:
            yield ChatCompletionStreamChunk(delta=delta)


class FakeCatalogWorkspace:
    def get_series_catalog(self, series_id: str):
        self.last_series_id = series_id
        return {
            "series_id": series_id,
            "series_title": "Series 1",
            "videos": [
                {"video_id": f"video-{index}", "title": f"Video {index}", "processed": True}
                for index in range(1, 6)
            ],
        }

    def list_series(self):
        return [FakeSeries("series-1", "Series 1")]


class FakeSeries:
    def __init__(self, series_id: str, title: str) -> None:
        self.id = series_id
        self.title = title
        self.videos = []


class FakeSessionStore:
    def __init__(self) -> None:
        self.last_append: dict[str, object] = {}

    def get_snapshot(self, session_id: str):
        del session_id
        return None

    def append_turn(self, **kwargs):
        self.last_append = kwargs


class FakeSnapshotStore:
    def __init__(self, snapshot: AgentSessionSnapshot | None) -> None:
        self._snapshot = snapshot
        self.last_append: dict[str, object] = {}

    def get_snapshot(self, session_id: str):
        del session_id
        return self._snapshot

    def append_turn(self, **kwargs):
        self.last_append = kwargs

    def clear_snapshot(self, session_id: str) -> None:
        del session_id
        self._snapshot = None


class FakeMessageCompactor:
    def compact_if_needed(self, messages: list[AgentChatMessage]) -> list[AgentChatMessage]:
        rendered = "、".join(message.content for message in messages)
        return [AgentChatMessage(role="system", content=f"更早对话摘要：{rendered}。")]


def builder_turn_result(message: str, citations_payload: list[dict[str, object]] | None = None):
    from backend.agent.schemas.action_plan import AgentActionPlan, AgentTurnResult, CitationReference

    return AgentTurnResult(
        assistant_message=message,
        plan=AgentActionPlan(scope_type=ScopeType.SERIES, reason="", tool_calls=[]),
        tool_results=[],
        citations=[
            CitationReference.model_validate(item)
            for item in (citations_payload or [])
        ],
    )


def video_graph_input(user_message: str) -> dict[str, object]:
    return {
        "session_id": "video|series-1|video-1",
        "scope_type": "video",
        "series_id": "series-1",
        "video_id": "video-1",
        "user_message": user_message,
        "memory_messages": [],
    }


def json_dumps(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
