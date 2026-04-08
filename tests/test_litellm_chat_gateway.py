from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.infrastructure.chat_gateway import LiteLLMChatGateway
from backend.agent.schemas.messages import AgentChatMessage


class LiteLLMChatGatewayTests(unittest.TestCase):
    def test_create_text_completion_uses_provider_normalized_model(self) -> None:
        captured_calls: list[dict[str, object]] = []

        def fake_completion(**kwargs):
            captured_calls.append(kwargs)
            return {"choices": [{"message": {"content": "你好，世界"}}]}

        gateway = LiteLLMChatGateway(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            completion_fn=fake_completion,
        )

        result = gateway.create_text_completion(
            [AgentChatMessage(role="user", content="你好")]
        )

        self.assertEqual(result, "你好，世界")
        self.assertEqual(captured_calls[0]["model"], "openai/gpt-5.4")
        self.assertEqual(captured_calls[0]["api_base"], "https://example.com/v1")
        self.assertEqual(captured_calls[0]["api_key"], "test-key")
        self.assertEqual(captured_calls[0]["temperature"], 0)

    def test_create_text_completion_stream_yields_all_delta_chunks(self) -> None:
        def fake_completion(**kwargs):
            self.assertTrue(kwargs["stream"])
            return iter(
                [
                    {"choices": [{"delta": {"content": "你"}}]},
                    {"choices": [{"delta": {"content": "好"}}]},
                    {"choices": [{"delta": {"content": "！"}}]},
                ]
            )

        gateway = LiteLLMChatGateway(
            provider="openai_compatible",
            model="openai/gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            completion_fn=fake_completion,
        )

        chunks = list(
            gateway.create_text_completion_stream(
                [AgentChatMessage(role="user", content="你好")]
            )
        )

        self.assertEqual(chunks, ["你", "好", "！"])

    def test_create_text_completion_falls_back_to_stream_when_non_stream_content_is_empty(self) -> None:
        def fake_completion(**kwargs):
            if kwargs.get("stream"):
                return iter(
                    [
                        {"choices": [{"delta": {"content": "回退"}}]},
                        {"choices": [{"delta": {"content": "成功"}}]},
                    ]
                )
            return {"choices": [{"message": {"content": None}}]}

        gateway = LiteLLMChatGateway(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            completion_fn=fake_completion,
        )

        result = gateway.create_text_completion(
            [AgentChatMessage(role="user", content="你好")]
        )

        self.assertEqual(result, "回退成功")

    def test_create_structured_completion_fails_fast(self) -> None:
        gateway = LiteLLMChatGateway(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            completion_fn=lambda **kwargs: kwargs,
        )

        with self.assertRaises(RuntimeError):
            gateway.create_structured_completion([], dict)  # type: ignore[arg-type]

    def test_unsupported_provider_fails_fast(self) -> None:
        with self.assertRaises(RuntimeError):
            LiteLLMChatGateway(
                provider="responses_api",
                model="gpt-5.4",
                base_url="https://example.com/v1",
                api_key="test-key",
                completion_fn=lambda **kwargs: kwargs,
            )


if __name__ == "__main__":
    unittest.main()
