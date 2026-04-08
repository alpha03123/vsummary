from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.infrastructure.chat_gateway import LiteLLMChatGateway
from backend.agent.schemas.messages import AgentChatMessage


class AgentGatewayPayload(BaseModel):
    status: str


class AgentGatewayTests(unittest.TestCase):
    def test_litellm_gateway_passes_api_root_base_url_to_completion(self) -> None:
        captured_calls: list[dict[str, object]] = []

        def fake_completion(**kwargs):
            captured_calls.append(kwargs)
            return {"choices": [{"message": {"content": "ok"}}]}

        gateway = LiteLLMChatGateway(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            completion_fn=fake_completion,
        )

        text = gateway.create_text_completion([AgentChatMessage(role="user", content="hello")])

        self.assertEqual(text, "ok")
        self.assertEqual(captured_calls[0]["api_key"], "test-key")
        self.assertEqual(captured_calls[0]["api_base"], "https://api.openai.com/v1")
        self.assertEqual(captured_calls[0]["model"], "openai/gpt-5.4")

    def test_litellm_gateway_supports_structured_completion(self) -> None:
        gateway = LiteLLMChatGateway(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            completion_fn=lambda **kwargs: {
                "choices": [{"message": {"content": '{"status":"ok"}'}}]
            },
        )

        payload = gateway.create_structured_completion(
            [AgentChatMessage(role="user", content="输出 JSON")],
            AgentGatewayPayload,
        )

        self.assertEqual(payload.status, "ok")


if __name__ == "__main__":
    unittest.main()
