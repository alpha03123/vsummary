from __future__ import annotations

import unittest

from tests import _path_setup  # noqa: F401

from backend.video_summary.infrastructure.litellm_web_search import LiteLLMNativeWebSearchGateway


class LiteLLMNativeWebSearchGatewayTests(unittest.TestCase):
    def test_search_passes_native_web_search_options_and_extracts_url_citations(self) -> None:
        completion = FakeSearchCompletion()
        gateway = LiteLLMNativeWebSearchGateway(
            provider="openai_compatible",
            model="gpt-5-search-api",
            base_url="https://api.example.com/v1",
            api_key="test-key",
            search_context_size="medium",
            completion_fn=completion,
        )

        results = gateway.search("查一下 LLMOps 最新情况", max_results=2, timeout_seconds=7)

        self.assertEqual(completion.last_request["web_search_options"], {"search_context_size": "medium"})
        self.assertEqual(completion.last_request["timeout"], 7)
        self.assertEqual(results, [
            {
                "title": "LLMOps Article",
                "url": "https://example.com/llmops",
                "text": "LLMOps 最新情况",
                "snippet": "LLMOps 最新情况",
            }
        ])

    def test_search_fails_when_provider_returns_no_citable_sources(self) -> None:
        gateway = LiteLLMNativeWebSearchGateway(
            provider="openai_compatible",
            model="gpt-5-search-api",
            base_url="https://api.example.com/v1",
            api_key="test-key",
            search_context_size="medium",
            completion_fn=FakeNoCitationCompletion(),
        )

        with self.assertRaisesRegex(RuntimeError, "未返回可引用来源"):
            gateway.search("查一下", max_results=2, timeout_seconds=7)


class FakeSearchCompletion:
    def __init__(self) -> None:
        self.last_request: dict[str, object] = {}

    def __call__(self, **kwargs):
        self.last_request = dict(kwargs)
        return {
            "choices": [
                {
                    "message": {
                        "content": "LLMOps 最新情况：供应商正在加强评测。",
                        "annotations": [
                            {
                                "url_citation": {
                                    "url": "https://example.com/llmops",
                                    "title": "LLMOps Article",
                                    "start_index": 0,
                                    "end_index": 11,
                                }
                            }
                        ],
                    }
                }
            ]
        }


class FakeNoCitationCompletion:
    def __call__(self, **kwargs):
        del kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": "没有来源",
                        "annotations": [],
                    }
                }
            ]
        }


if __name__ == "__main__":
    unittest.main()
