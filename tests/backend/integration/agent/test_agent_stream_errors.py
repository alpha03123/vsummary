from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from tests import _path_setup  # noqa: F401

from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.infrastructure.chat_gateway import LiteLLMChatGateway
from backend.agent.memory.context import AgentContext
from backend.api.app import create_app
from backend.api.bootstrap import LazyAgentRuntimeProvider
from backend.agent_graph.actions.video_action_planner import VideoActionPlanner
from backend.agent_graph.query.series_answer_synthesizer import SeriesAnswerSynthesizer
from backend.agent_graph.query.series_query_processor import SeriesQueryProcessor
from backend.agent_graph.query.video_answer_synthesizer import AnswerSynthesisProgram
from backend.agent_graph.runtime.graph import build_agent_graph
from backend.agent_graph.runtime.service import AgentGraphService


class AgentStreamErrorTests(unittest.TestCase):
    def test_stream_converts_unhandled_model_error_to_sse_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = FakeContainer(Path(temp_dir), RuntimeError("litellm.APIError: APIError: OpenAIException - Your request was blocked."))
            client = TestClient(create_app(container))

            response = client.post(
                "/api/agent/chat/stream",
                json={
                    "session_id": "video|series-1|video-1|studio",
                    "message": "总结一下",
                    "context": {"scope_type": "video", "series_id": "series-1", "video_id": "video-1"},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: error", response.text)
        self.assertIn("模型请求被上游网关拦截", response.text)

    def test_series_talk_with_wrong_model_base_url_reports_model_service_error_after_understand_query(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = GraphServiceContainer(Path(temp_dir), _build_bad_base_url_agent_service("series"))
            client = TestClient(create_app(container))

            response = client.post(
                "/api/agent/chat/stream",
                json={
                    "session_id": "series|series-1|series-home",
                    "message": "这个系列讲了什么？",
                    "context": {"scope_type": "series", "series_id": "series-1"},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('"node_id": "understand_query"', response.text)
        self.assertIn('"label": "理解问题"', response.text)
        self.assertIn("event: error", response.text)
        self.assertIn("url连接错误，请检查拼写或者地址是否可用", response.text)
        self.assertNotIn("InternalServerError", response.text)
        self.assertNotIn("OpenAIException - Connection error.", response.text)

    def test_video_talk_with_wrong_model_base_url_reports_model_service_error_after_video_action_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = GraphServiceContainer(Path(temp_dir), _build_bad_base_url_agent_service("video"))
            client = TestClient(create_app(container))

            response = client.post(
                "/api/agent/chat/stream",
                json={
                    "session_id": "video|series-1|video-1|studio",
                    "message": "总结一下这个视频",
                    "context": {"scope_type": "video", "series_id": "series-1", "video_id": "video-1"},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('"node_id": "plan_and_execute_video_actions"', response.text)
        self.assertIn('"label": "规划并执行"', response.text)
        self.assertIn("event: error", response.text)
        self.assertIn("url连接错误，请检查拼写或者地址是否可用", response.text)
        self.assertNotIn("InternalServerError", response.text)
        self.assertNotIn("OpenAIException - Connection error.", response.text)

    def test_non_stream_converts_unhandled_model_error_to_503(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = FakeContainer(Path(temp_dir), RuntimeError("boom"))
            client = TestClient(create_app(container))

            response = client.post(
                "/api/agent/chat",
                json={
                    "session_id": "video|series-1|video-1|studio",
                    "message": "总结一下",
                    "context": {"scope_type": "video", "series_id": "series-1", "video_id": "video-1"},
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "boom")

    def test_non_stream_reports_unsupported_web_search_model_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = FakeContainer(Path(temp_dir), RuntimeError("Unsupported parameter: web_search_options"))
            client = TestClient(create_app(container))

            response = client.post(
                "/api/agent/chat",
                json={
                    "session_id": "video|series-1|video-1|studio",
                    "message": "联网查一下",
                    "context": {"scope_type": "video", "series_id": "series-1", "video_id": "video-1"},
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "联网搜索失败：当前模型或供应商不支持联网搜索，请关闭联网搜索或更换支持搜索的模型。",
        )

    def test_stream_reports_web_search_timeout_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = FakeContainer(Path(temp_dir), TimeoutError("web_search request timed out"))
            client = TestClient(create_app(container))

            response = client.post(
                "/api/agent/chat/stream",
                json={
                    "session_id": "video|series-1|video-1|studio",
                    "message": "联网查一下",
                    "context": {"scope_type": "video", "series_id": "series-1", "video_id": "video-1"},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("联网搜索失败：请求超时，请稍后重试或关闭联网搜索。", response.text)

    def test_web_search_gateway_factory_rejects_unsupported_provider_mode(self) -> None:
        provider = LazyAgentRuntimeProvider(
            root_dir=Path("."),
            workspace=None,
            rag_model_manager=None,
        )

        with self.assertRaisesRegex(RuntimeError, "Unsupported web_search provider/mode"):
            provider._build_web_search_gateway(
                settings=FakeSettings(
                    web_search=FakeWebSearchSettings(
                        enabled=True,
                        provider="litellm",
                        mode="unsupported",
                    )
                ),
                env_settings=FakeEnvSettings(),
            )


class FakeContainer:
    def __init__(self, root_dir: Path, error: Exception) -> None:
        self.root_dir = root_dir
        self.config_path = root_dir / "config" / "settings.toml"
        self.rag_model_manager = None
        self._error = error

    def get_agent_graph_service(self):
        return FakeAgentGraphService(self._error)


class GraphServiceContainer:
    def __init__(self, root_dir: Path, service: AgentGraphService) -> None:
        self.root_dir = root_dir
        self.config_path = root_dir / "config" / "settings.toml"
        self.rag_model_manager = None
        self._service = service

    def get_agent_graph_service(self):
        return self._service


class FakeSettings:
    def __init__(self, *, web_search) -> None:
        self.web_search = web_search


class FakeWebSearchSettings:
    def __init__(self, *, enabled: bool, provider: str, mode: str) -> None:
        self.enabled = enabled
        self.provider = provider
        self.mode = mode
        self.search_context_size = "medium"


class FakeEnvSettings:
    provider = "openai"
    model = "test-model"
    base_url = "https://api.example.com/v1"
    api_key = "test-key"


class FakeAgentGraphService:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def stream_with_context(self, **kwargs):
        del kwargs
        raise self._error

    def run_turn(self, **kwargs):
        del kwargs
        raise self._error


class FakeWorkspace:
    def get_series_catalog(self, series_id: str):
        return {
            "series_id": series_id,
            "videos": [{"video_id": "video-1", "title": "Video 1"}],
        }

    def list_series(self):
        return [SimpleNamespace(id="series-1", title="Series 1")]

    def get_video_summary(self, series_id: str, video_id: str):
        return SimpleNamespace(
            series_id=series_id,
            video_id=video_id,
            title="Video 1",
            summary={
                "one_sentence_summary": "这个视频介绍测试内容。",
                "core_problem": "如何复现模型接口错误。",
                "key_takeaways": ["错误需要清晰暴露"],
            },
        )

    def get_video_transcript(self, series_id: str, video_id: str):
        return SimpleNamespace(
            series_id=series_id,
            video_id=video_id,
            title="Video 1",
            segments=[
                SimpleNamespace(
                    start_seconds=0.0,
                    end_seconds=3.0,
                    text="这里是一段测试转写。",
                )
            ],
        )


class FakeRetrievalService:
    def default_max_hits(self) -> int:
        return 3

    def search(self, **kwargs):
        return {
            "hits": [
                {
                    "doc_id": "series:series-1:video:video-1:summary",
                    "series_id": kwargs.get("series_id", "series-1"),
                    "video_id": kwargs.get("video_id", "video-1") or "video-1",
                    "source_type": "summary_global",
                    "source_family": "summary",
                    "title": "Video 1",
                    "text": "测试证据",
                    "snippet": "测试证据",
                    "score": 0.9,
                }
            ]
        }


class FakeToolExecutor:
    def execute_call(self, call, context):
        raise AssertionError("bad base URL should fail before executing video tools")


class DisabledWebSearchSettings:
    enabled = False


def _build_bad_base_url_agent_service(scope_type: str) -> AgentGraphService:
    gateway = LiteLLMChatGateway(
        provider="openai",
        model="gpt-5.4",
        base_url="http://127.0.0.1:9",
        api_key="sk-test",
    )
    workspace = FakeWorkspace()
    retrieval_service = FakeRetrievalService()
    graph = build_agent_graph(
        retrieval_service=retrieval_service,
        answer_program=AnswerSynthesisProgram(gateway=gateway),
        series_query_processor=SeriesQueryProcessor(gateway=gateway),
        series_answer_synthesizer=SeriesAnswerSynthesizer(gateway=gateway),
        workspace=workspace,
        video_action_planner=VideoActionPlanner(gateway=gateway),
        tool_executor=FakeToolExecutor(),
        web_search_settings=DisabledWebSearchSettings(),
    )
    context = AgentContext(
        session_id="series|series-1|series-home" if scope_type == "series" else "video|series-1|video-1|studio",
        scope_type=scope_type,
        series_id="series-1",
        video_id="" if scope_type == "series" else "video-1",
    )
    return AgentGraphService(
        context_loader=StaticAgentContextLoader(context),
        graph=graph,
        answer_stream_gateway=gateway,
    )


if __name__ == "__main__":
    unittest.main()
