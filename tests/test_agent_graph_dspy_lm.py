from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy.dspy_lm import ProxyStreamingLM


class _FakeResponse:
    def __init__(self, lines: list[bytes], status_code: int = 200) -> None:
        self.status_code = status_code
        self._lines = lines

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def iter_lines(self, decode_unicode: bool = False):
        del decode_unicode
        for line in self._lines:
            yield line


class AgentGraphDspyLMTests(unittest.TestCase):
    def test_proxy_streaming_lm_assembles_delta_content(self) -> None:
        fake_lines = [
            b'data: {"choices":[{"delta":{"content":"\\u6cd5\\u56fd"}}]}',
            b'data: {"choices":[{"delta":{"content":"\\u9996\\u90fd"}}]}',
            b'data: {"choices":[{"delta":{"content":"\\u662f\\u5df4\\u9ece\\u3002"}}],"usage":{"total_tokens":12}}',
            b"data: [DONE]",
        ]

        lm = ProxyStreamingLM(
            model="openai/gpt-5.4",
            api_base="http://127.0.0.1:8317/v1",
            api_key="test-key",
            request_sender=lambda **kwargs: _FakeResponse(fake_lines),
        )

        response = lm.forward(messages=[{"role": "user", "content": "法国首都是什么？"}])

        self.assertEqual(response.choices[0].message.content, "法国首都是巴黎。")
        self.assertEqual(response.usage["total_tokens"], 12)


if __name__ == "__main__":
    unittest.main()
