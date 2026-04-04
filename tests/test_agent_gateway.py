from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.infrastructure.chat_gateway import OpenAICompatibleChatGateway
from backend.agent.schemas.messages import AgentChatMessage


class FakeOpenAIClient:
    def __init__(self, *, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=self._create,
            )
        )
        self.beta = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    parse=self._parse,
                )
            )
        )

    def _create(self, **_: object):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    def _parse(self, **kwargs: object):
        response_model = kwargs["response_format"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=response_model(value="ok")))]
        )


class FakeResponseModel:
    def __init__(self, value: str) -> None:
        self.value = value


class AgentGatewayTests(unittest.TestCase):
    def test_openai_gateway_passes_api_root_base_url_to_sdk(self) -> None:
        fake_module = ModuleType("openai")
        captured: dict[str, str] = {}

        def build_client(*, api_key: str, base_url: str):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            return FakeOpenAIClient(api_key=api_key, base_url=base_url)

        fake_module.OpenAI = build_client
        original_module = sys.modules.get("openai")
        sys.modules["openai"] = fake_module
        try:
            gateway = OpenAICompatibleChatGateway(
                model="gpt-5.4",
                base_url="https://api.openai.com/v1",
                api_key="test-key",
            )

            text = gateway.create_text_completion([AgentChatMessage(role="user", content="hello")])
            parsed = gateway.create_structured_completion(
                [AgentChatMessage(role="user", content="hello")],
                FakeResponseModel,
            )

            self.assertEqual(text, "ok")
            self.assertEqual(parsed.value, "ok")
            self.assertEqual(captured["api_key"], "test-key")
            self.assertEqual(captured["base_url"], "https://api.openai.com/v1")
        finally:
            if original_module is None:
                sys.modules.pop("openai", None)
            else:
                sys.modules["openai"] = original_module


if __name__ == "__main__":
    unittest.main()
