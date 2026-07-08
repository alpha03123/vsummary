from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests import _path_setup  # noqa: F401

from backend.api.http.app import create_app
from backend.api.adapters.agent_runtime_provider import LazyAgentRuntimeProvider


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


if __name__ == "__main__":
    unittest.main()
