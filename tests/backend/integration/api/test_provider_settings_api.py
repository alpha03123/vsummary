from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests import _path_setup  # noqa: F401

from backend.api.app import create_app
from backend.video_summary.infrastructure.settings_service import ProviderSettings


class ProviderSettingsApiTests(unittest.TestCase):
    def test_updating_provider_settings_invalidates_cached_agent_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = FakeContainer(Path(temp_dir))
            client = TestClient(create_app(container))

            response = client.put(
                "/api/provider-settings",
                json={
                    "llm_provider": "openai",
                    "openai_base_url": "http://127.0.0.1:8317",
                    "openai_model": "gpt-5.4",
                    "openai_api_key": "sk-test",
                    "hf_endpoint": "https://hf-mirror.com",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(container.invalidate_agent_graph_service_calls, 1)

    def test_provider_settings_test_returns_model_connection_error_without_agent_stage_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = FakeContainer(
                Path(temp_dir),
                settings_service=FailingSettingsService(
                    RuntimeError("APIConnectionError: Connection refused")
                ),
            )
            client = TestClient(create_app(container))

            response = client.post(
                "/api/provider-settings/test",
                json={
                    "llm_provider": "deepseek",
                    "openai_base_url": "http://127.0.0.1:8317",
                    "openai_model": "gpt-5.4",
                    "openai_api_key": "sk-test",
                    "hf_endpoint": "https://hf-mirror.com",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "APIConnectionError: Connection refused")
        self.assertNotIn("理解问题", response.json()["detail"])


class FakeContainer:
    def __init__(self, root_dir: Path, *, settings_service=None) -> None:
        self.root_dir = root_dir
        self.config_path = root_dir / "config" / "settings.toml"
        self.settings_service = settings_service or FakeSettingsService()
        self.invalidate_agent_graph_service_calls = 0

    def invalidate_agent_graph_service(self) -> None:
        self.invalidate_agent_graph_service_calls += 1


class FakeSettingsService:
    def update_provider_settings(self, **kwargs) -> ProviderSettings:
        return ProviderSettings(
            llm_provider=kwargs["llm_provider"],
            openai_base_url=kwargs["openai_base_url"],
            openai_model=kwargs["openai_model"],
            has_openai_api_key=bool(kwargs["openai_api_key"]),
            openai_api_key_masked="sk-****test",
            hf_endpoint=kwargs["hf_endpoint"],
        )


class FailingSettingsService(FakeSettingsService):
    def __init__(self, error: Exception) -> None:
        self._error = error

    def test_provider_settings(self, **kwargs) -> str:
        del kwargs
        raise self._error


if __name__ == "__main__":
    unittest.main()
