from __future__ import annotations

import asyncio
import sys
from pathlib import Path
import unittest


from pydantic import BaseModel

from backend.shared.llm.litellm_gateway import LiteLLMCompletionGateway, clear_structured_mode_cache
from backend.agent_graph.query.models import SeriesAnswerPayload


class LiteLLMCompletionGatewayStructuredModeTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_structured_mode_cache()

    def test_uses_litellm_pydantic_schema_first_for_openai_models(self) -> None:
        completion = CapturingCompletion(
            '{"answer": "ok", "citations": ["e1"], "used_source_types": ["transcript"]}'
        )
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        result = gateway.complete_structured(
            [{"role": "user", "content": "回答问题"}],
            response_model=SeriesAnswerPayload,
        )

        self.assertEqual(result.citations, ["e1"])
        self.assertIs(completion.response_formats[0], SeriesAnswerPayload)
        prompt = "\n".join(str(message["content"]) for message in completion.messages[0])
        self.assertNotIn("JSON Schema", prompt)

    def test_adds_v1_suffix_to_root_base_url_for_requests(self) -> None:
        completion = CapturingCompletion("ok")
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://jiuuij.de5.net",
            api_key="test-key",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        result = gateway.complete_text([{"role": "user", "content": "ping"}])

        self.assertEqual(result, "ok")
        self.assertEqual(completion.api_bases, ["https://jiuuij.de5.net/v1"])

    def test_keeps_existing_v1_suffix_for_requests(self) -> None:
        completion = CapturingCompletion("ok")
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://jiuuij.de5.net/v1/",
            api_key="test-key",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        gateway.complete_text([{"role": "user", "content": "ping"}])

        self.assertEqual(completion.api_bases, ["https://jiuuij.de5.net/v1"])

    def test_passes_reasoning_effort_to_litellm_requests(self) -> None:
        completion = CapturingCompletion("ok")
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            reasoning_effort="high",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        gateway.complete_text([{"role": "user", "content": "ping"}])

        self.assertEqual(completion.reasoning_efforts, ["high"])

    def test_allows_reasoning_effort_for_openai_compatible_custom_models(self) -> None:
        completion = CapturingCompletion("ok")
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="deepseek-v4-pro",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            reasoning_effort="medium",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        gateway.complete_text([{"role": "user", "content": "ping"}])

        self.assertEqual(completion.allowed_openai_params, [["reasoning_effort"]])

    def test_omits_reasoning_effort_when_disabled(self) -> None:
        completion = CapturingCompletion("ok")
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            reasoning_effort="none",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        gateway.complete_text([{"role": "user", "content": "ping"}])

        self.assertEqual(completion.reasoning_efforts, [None])

    def test_raises_clear_error_when_reasoning_effort_is_not_supported(self) -> None:
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            reasoning_effort="high",
            completion_fn=RejectingReasoningEffortCompletion(),
            acompletion_fn=unused_async_completion,
        )

        with self.assertRaisesRegex(RuntimeError, "此模型不支持思考强度"):
            gateway.complete_text([{"role": "user", "content": "ping"}])

    def test_uses_litellm_provider_prefix_for_bare_model_names(self) -> None:
        completion = CapturingCompletion("ok")
        gateway = LiteLLMCompletionGateway(
            provider="deepseek",
            model="deepseek-v4-pro",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        gateway.complete_text([{"role": "user", "content": "ping"}])

        self.assertEqual(completion.models, ["deepseek/deepseek-v4-pro"])

    def test_stream_text_wraps_reasoning_content_as_think_block(self) -> None:
        gateway = LiteLLMCompletionGateway(
            provider="deepseek",
            model="deepseek-reasoner",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            completion_fn=ReasoningStreamCompletion(),
            acompletion_fn=unused_async_completion,
        )

        chunks = list(gateway.stream_text([{"role": "user", "content": "ping"}]))

        self.assertEqual(chunks, ["<think>", "先分析。", "</think>", "最终答案。"])

    def test_allows_ollama_without_api_key(self) -> None:
        completion = CapturingCompletion("ok")
        gateway = LiteLLMCompletionGateway(
            provider="ollama",
            model="qwen2.5:7b",
            base_url="http://127.0.0.1:11434",
            api_key="",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        gateway.complete_text([{"role": "user", "content": "ping"}])

        self.assertEqual(completion.models, ["ollama/qwen2.5:7b"])
        self.assertEqual(completion.api_keys, [None])
        self.assertEqual(completion.api_bases, ["http://127.0.0.1:11434"])

    def test_keeps_api_key_required_for_openai_provider(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "缺少 API Key"):
            LiteLLMCompletionGateway(
                provider="openai",
                model="test-model",
                base_url="https://example.invalid/v1",
                api_key="",
                completion_fn=CapturingCompletion("ok"),
                acompletion_fn=unused_async_completion,
            )

    def test_falls_back_to_json_object_when_schema_is_rejected(self) -> None:
        completion = RejectingFirstResponseFormatCompletion(
            SeriesAnswerPayload,
            '{"answer": "ok", "citations": ["e1"], "used_source_types": ["transcript"]}',
        )
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        result = gateway.complete_structured(
            [{"role": "user", "content": "回答问题"}],
            response_model=SeriesAnswerPayload,
        )

        self.assertEqual(result.citations, ["e1"])
        self.assertEqual(completion.response_formats, [SeriesAnswerPayload, {"type": "json_object"}])
        prompt = "\n".join(str(message["content"]) for message in completion.messages[1])
        self.assertIn("只输出一个 JSON 对象", prompt)
        self.assertNotIn("JSON Schema", prompt)

    def test_caches_schema_mode_after_success_for_same_endpoint(self) -> None:
        completion = CapturingCompletion(
            '{"answer": "ok", "citations": ["e1"], "used_source_types": ["transcript"]}'
        )
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        gateway.complete_structured(
            [{"role": "user", "content": "第一次"}],
            response_model=SeriesAnswerPayload,
        )
        gateway.complete_structured(
            [{"role": "user", "content": "第二次"}],
            response_model=SeriesAnswerPayload,
        )

        self.assertEqual(completion.response_formats, [SeriesAnswerPayload, SeriesAnswerPayload])

    def test_cached_schema_mode_falls_back_when_later_schema_is_rejected(self) -> None:
        completion = RejectingBaseModelResponseFormatsCompletion(
            '{"answer": "ok", "citations": ["e1"], "used_source_types": ["transcript"]}'
        )
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        gateway.complete_structured(
            [{"role": "user", "content": "第一次"}],
            response_model=SeriesAnswerPayload,
        )
        result = gateway.complete_structured(
            [{"role": "user", "content": "第二次"}],
            response_model=SeriesAnswerPayload,
        )

        self.assertEqual(result.citations, ["e1"])
        self.assertEqual(
            completion.response_formats,
            [SeriesAnswerPayload, SeriesAnswerPayload, {"type": "json_object"}],
        )

    def test_caches_json_object_mode_after_schema_rejection_for_same_endpoint(self) -> None:
        completion = RejectingFirstResponseFormatCompletion(
            SeriesAnswerPayload,
            '{"answer": "ok", "citations": ["e1"], "used_source_types": ["transcript"]}',
        )
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        gateway.complete_structured(
            [{"role": "user", "content": "第一次"}],
            response_model=SeriesAnswerPayload,
        )
        gateway.complete_structured(
            [{"role": "user", "content": "第二次"}],
            response_model=SeriesAnswerPayload,
        )

        self.assertEqual(
            completion.response_formats,
            [SeriesAnswerPayload, {"type": "json_object"}, {"type": "json_object"}],
        )

    def test_cache_is_scoped_by_api_key(self) -> None:
        first_completion = RejectingFirstResponseFormatCompletion(
            SeriesAnswerPayload,
            '{"answer": "ok", "citations": ["e1"], "used_source_types": ["transcript"]}',
        )
        first_gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="first-key",
            completion_fn=first_completion,
            acompletion_fn=unused_async_completion,
        )
        second_completion = CapturingCompletion(
            '{"answer": "ok", "citations": ["e1"], "used_source_types": ["transcript"]}'
        )
        second_gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="second-key",
            completion_fn=second_completion,
            acompletion_fn=unused_async_completion,
        )

        first_gateway.complete_structured(
            [{"role": "user", "content": "第一次"}],
            response_model=SeriesAnswerPayload,
        )
        second_gateway.complete_structured(
            [{"role": "user", "content": "第二次"}],
            response_model=SeriesAnswerPayload,
        )

        self.assertEqual(first_completion.response_formats, [SeriesAnswerPayload, {"type": "json_object"}])
        self.assertEqual(second_completion.response_formats, [SeriesAnswerPayload])

    def test_falls_back_to_prompt_schema_when_response_format_is_rejected(self) -> None:
        completion = RejectingResponseFormatsCompletion(
            '{"answer": "ok", "citations": ["e1"], "used_source_types": ["transcript"]}'
        )
        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            completion_fn=completion,
            acompletion_fn=unused_async_completion,
        )

        result = gateway.complete_structured(
            [{"role": "user", "content": "回答问题"}],
            response_model=SeriesAnswerPayload,
        )

        self.assertEqual(result.citations, ["e1"])
        self.assertEqual(completion.response_formats, [SeriesAnswerPayload, {"type": "json_object"}, None])
        prompt = "\n".join(str(message["content"]) for message in completion.messages[2])
        self.assertIn("只输出一个 JSON 对象", prompt)
        self.assertIn("不要输出 Markdown", prompt)
        self.assertIn('"SeriesAnswerPayload"', prompt)
        self.assertIn('"citations"', prompt)

    def test_async_acomplete_structured_forwards_timeout_to_acompletion(self) -> None:
        # T1: explicit timeout reaches the litellm layer.
        #
        # Uses SeriesAnswerPayload (already imported at top of file) instead of
        # MindmapNodePayload: the timeout-forwarding logic is independent of the
        # response_model type (acomplete_structured is generic over
        # type[StructuredResponseT] and does not dispatch on it). Keeping
        # SeriesAnswerPayload avoids pulling video_summary.generation into this
        # shared-layer test.
        recorded_timeouts: list[object] = []

        async def recording_acompletion(**kwargs):
            recorded_timeouts.append(kwargs.get("timeout"))
            return {"choices": [{"message": {"content": '{"answer": "ok", "citations": [], "used_source_types": []}'}}]}

        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            acompletion_fn=recording_acompletion,
        )

        result = asyncio.run(
            gateway.acomplete_structured(
                [{"role": "user", "content": "生成思维导图"}],
                response_model=SeriesAnswerPayload,
                timeout=120,
            )
        )

        self.assertEqual(result.answer, "ok")
        self.assertEqual(recorded_timeouts, [120])

    def test_async_acomplete_structured_default_timeout_is_none(self) -> None:
        # T2: when timeout is omitted, inner acomplete_text sees None.
        recorded_timeouts: list[object] = []

        async def recording_acompletion(**kwargs):
            recorded_timeouts.append(kwargs.get("timeout"))
            return {"choices": [{"message": {"content": '{"answer": "ok", "citations": [], "used_source_types": []}'}}]}

        gateway = LiteLLMCompletionGateway(
            provider="openai",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            acompletion_fn=recording_acompletion,
        )

        asyncio.run(
            gateway.acomplete_structured(
                [{"role": "user", "content": "生成思维导图"}],
                response_model=SeriesAnswerPayload,
            )
        )

        self.assertEqual(recorded_timeouts, [None])


class CapturingCompletion:
    def __init__(self, content: str) -> None:
        self._content = content
        self.messages: list[list[dict[str, object]]] = []
        self.response_formats: list[object] = []
        self.api_bases: list[str] = []
        self.reasoning_efforts: list[object] = []
        self.allowed_openai_params: list[object] = []
        self.models: list[str] = []
        self.api_keys: list[object] = []

    def __call__(self, **kwargs):
        self.messages.append(list(kwargs["messages"]))
        self.response_formats.append(kwargs.get("response_format"))
        self.api_bases.append(kwargs["api_base"])
        self.reasoning_efforts.append(kwargs.get("reasoning_effort"))
        self.allowed_openai_params.append(kwargs.get("allowed_openai_params"))
        self.models.append(kwargs["model"])
        self.api_keys.append(kwargs.get("api_key"))
        return {"choices": [{"message": {"content": self._content}}]}


class RejectingFirstResponseFormatCompletion(CapturingCompletion):
    def __init__(self, rejected_format: object, content: str) -> None:
        super().__init__(content)
        self._rejected_format = rejected_format

    def __call__(self, **kwargs):
        self.messages.append(list(kwargs["messages"]))
        response_format = kwargs.get("response_format")
        self.response_formats.append(response_format)
        if response_format is self._rejected_format:
            raise RuntimeError("response_format json_schema is not supported")
        return {"choices": [{"message": {"content": self._content}}]}


class RejectingResponseFormatsCompletion(CapturingCompletion):
    def __call__(self, **kwargs):
        self.messages.append(list(kwargs["messages"]))
        response_format = kwargs.get("response_format")
        self.response_formats.append(response_format)
        if response_format is not None:
            raise RuntimeError("response_format is not supported")
        return {"choices": [{"message": {"content": self._content}}]}


class RejectingBaseModelResponseFormatsCompletion(CapturingCompletion):
    def __init__(self, content: str) -> None:
        super().__init__(content)
        self._has_seen_schema_success = False

    def __call__(self, **kwargs):
        self.messages.append(list(kwargs["messages"]))
        response_format = kwargs.get("response_format")
        self.response_formats.append(response_format)
        if isinstance(response_format, type) and issubclass(response_format, BaseModel):
            if self._has_seen_schema_success:
                raise RuntimeError("response_format json_schema is not supported")
            self._has_seen_schema_success = True
        return {"choices": [{"message": {"content": self._content}}]}


class RejectingReasoningEffortCompletion:
    def __call__(self, **kwargs):
        del kwargs
        raise RuntimeError("openai does not support parameters: ['reasoning_effort']")


class ReasoningStreamCompletion:
    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return iter(
            [
                {"choices": [{"delta": {"reasoning_content": "先分析。"}}]},
                {"choices": [{"delta": {"content": "最终答案。"}}]},
            ]
        )


async def unused_async_completion(**kwargs):
    del kwargs
    raise AssertionError("async completion should not be called")


if __name__ == "__main__":
    unittest.main()
