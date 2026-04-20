from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from backend.agent.schemas.chat_stream import ChatCompletionStreamChunk
from backend.shared.llm.json_mode import describe_validation_error, validate_json_response


StructuredResponseT = TypeVar("StructuredResponseT", bound=BaseModel)
CompletionFn = Callable[..., Any]
AsyncCompletionFn = Callable[..., Awaitable[Any]]


class LiteLLMCompletionGateway:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        completion_fn: CompletionFn | None = None,
        acompletion_fn: AsyncCompletionFn | None = None,
    ) -> None:
        normalized_api_key = api_key.strip()
        if not normalized_api_key:
            raise RuntimeError("缺少 API Key，无法调用模型。")

        self._provider = provider.strip()
        self._model = _normalize_litellm_model(self._provider, model)
        self._base_url = base_url.rstrip("/")
        self._api_key = normalized_api_key
        self._completion = completion_fn or _load_litellm_completion()
        self._acompletion = acompletion_fn or _load_litellm_acompletion()

    def complete_text(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0,
        response_format: dict[str, Any] | type[BaseModel] | None = None,
    ) -> str:
        response = self._completion(
            model=self._model,
            messages=_dump_messages(messages),
            api_base=self._base_url,
            api_key=self._api_key,
            temperature=temperature,
            response_format=response_format,
        )
        content = _extract_completion_content(response)
        if content.strip():
            return content.strip()
        fallback_chunks = list(self.stream_text(messages, temperature=temperature))
        fallback_content = "".join(fallback_chunks).strip()
        if fallback_content:
            return fallback_content
        raise RuntimeError("模型返回缺少 message.content。")

    async def acomplete_text(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0,
        response_format: dict[str, Any] | type[BaseModel] | None = None,
    ) -> str:
        response = await self._acompletion(
            model=self._model,
            messages=_dump_messages(messages),
            api_base=self._base_url,
            api_key=self._api_key,
            temperature=temperature,
            response_format=response_format,
        )
        content = _extract_completion_content(response)
        if content.strip():
            return content.strip()
        fallback_chunks = [
            chunk
            async for chunk in self.astream_text(
                messages,
                temperature=temperature,
                response_format=response_format,
            )
        ]
        fallback_content = "".join(fallback_chunks).strip()
        if fallback_content:
            return fallback_content
        raise RuntimeError("模型返回缺少 message.content。")

    def stream_text(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0,
        response_format: dict[str, Any] | type[BaseModel] | None = None,
    ) -> Iterator[str]:
        stream = self._completion(
            model=self._model,
            messages=_dump_messages(messages),
            api_base=self._base_url,
            api_key=self._api_key,
            temperature=temperature,
            stream=True,
            response_format=response_format,
        )
        for chunk in stream:
            delta = _extract_stream_delta(chunk)
            if delta:
                yield delta

    def stream_text_with_metadata(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0,
        response_format: dict[str, Any] | type[BaseModel] | None = None,
    ) -> Iterator[ChatCompletionStreamChunk]:
        stream = self._completion(
            model=self._model,
            messages=_dump_messages(messages),
            api_base=self._base_url,
            api_key=self._api_key,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
            response_format=response_format,
        )
        final_usage: dict[str, int] = {}
        for chunk in stream:
            delta = _extract_stream_delta(chunk)
            usage = _extract_usage(chunk)
            if usage:
                final_usage = usage
            if delta:
                yield ChatCompletionStreamChunk(delta=delta)
        if final_usage:
            yield ChatCompletionStreamChunk(usage=final_usage)

    async def astream_text(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0,
        response_format: dict[str, Any] | type[BaseModel] | None = None,
    ):
        stream = await self._acompletion(
            model=self._model,
            messages=_dump_messages(messages),
            api_base=self._base_url,
            api_key=self._api_key,
            temperature=temperature,
            stream=True,
            response_format=response_format,
        )
        async for chunk in stream:
            delta = _extract_stream_delta(chunk)
            if delta:
                yield delta

    def complete_structured(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        response_model: type[StructuredResponseT],
        temperature: float = 0,
        retries: int = 2,
    ) -> StructuredResponseT:
        validation_error: str | None = None
        last_raw_text = ""

        for attempt_index in range(retries + 1):
            structured_messages = _build_retry_messages(messages=messages, validation_error=validation_error)
            last_raw_text = self.complete_text(
                structured_messages,
                temperature=temperature,
                response_format=response_model,
            )
            try:
                validated = validate_json_response(
                    raw_text=last_raw_text,
                    response_model=response_model,
                )
                return validated  # type: ignore[return-value]
            except Exception as error:
                validation_error = describe_validation_error(error)
                if attempt_index == retries:
                    raise RuntimeError(
                        "LiteLLM 结构化请求失败: "
                        f"{validation_error}\n原始输出:\n{last_raw_text}"
                    ) from error

        raise RuntimeError("LiteLLM 结构化请求失败: 未知错误。")

    async def acomplete_structured(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        response_model: type[StructuredResponseT],
        temperature: float = 0,
        retries: int = 2,
    ) -> StructuredResponseT:
        validation_error: str | None = None
        last_raw_text = ""

        for attempt_index in range(retries + 1):
            structured_messages = _build_retry_messages(messages=messages, validation_error=validation_error)
            last_raw_text = await self.acomplete_text(
                structured_messages,
                temperature=temperature,
                response_format=response_model,
            )
            try:
                validated = validate_json_response(
                    raw_text=last_raw_text,
                    response_model=response_model,
                )
                return validated  # type: ignore[return-value]
            except Exception as error:
                validation_error = describe_validation_error(error)
                if attempt_index == retries:
                    raise RuntimeError(
                        "LiteLLM 结构化请求失败: "
                        f"{validation_error}\n原始输出:\n{last_raw_text}"
                    ) from error

        raise RuntimeError("LiteLLM 结构化请求失败: 未知错误。")


def _load_litellm_completion() -> CompletionFn:
    try:
        from litellm import completion
    except ModuleNotFoundError as error:
        raise RuntimeError("缺少 litellm 依赖，无法调用模型。") from error
    return completion


def _load_litellm_acompletion() -> AsyncCompletionFn:
    try:
        from litellm import acompletion
    except ModuleNotFoundError as error:
        raise RuntimeError("缺少 litellm 依赖，无法调用模型。") from error
    return acompletion


def _normalize_litellm_model(provider: str, model: str) -> str:
    normalized_model = model.strip()
    if not normalized_model:
        raise RuntimeError("缺少模型名称，无法调用模型。")
    if provider != "openai_compatible":
        raise RuntimeError(f"unsupported llm provider '{provider}'")
    if "/" in normalized_model:
        return normalized_model
    return f"openai/{normalized_model}"


def _dump_messages(messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(message) for message in messages]


def _build_retry_messages(
    *,
    messages: Sequence[dict[str, Any]],
    validation_error: str | None,
) -> list[dict[str, Any]]:
    if not validation_error:
        return _dump_messages(messages)
    return [
        *_dump_messages(messages),
        {
            "role": "user",
            "content": (
                "上一轮结构化输出没有通过本地校验，请修正后重新输出。\n"
                f"校验错误：{validation_error}"
            ),
        },
    ]


def _extract_completion_content(response: Any) -> str:
    choices = _lookup(response, "choices")
    if not isinstance(choices, Sequence) or not choices:
        return ""
    message = _lookup(choices[0], "message")
    tool_call_content = _extract_tool_call_arguments(_lookup(message, "tool_calls"))
    if tool_call_content:
        return tool_call_content
    content = _lookup(message, "content")
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        parts = [part for part in (_extract_text_part(item) for item in content) if part]
        return "".join(parts)
    return ""


def _extract_stream_delta(chunk: Any) -> str:
    choices = _lookup(chunk, "choices")
    if not isinstance(choices, Sequence) or not choices:
        return ""
    delta = _lookup(choices[0], "delta")
    tool_call_content = _extract_tool_call_arguments(_lookup(delta, "tool_calls"))
    if tool_call_content:
        return tool_call_content
    content = _lookup(delta, "content")
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        parts = [part for part in (_extract_text_part(item) for item in content) if part]
        return "".join(parts)
    return ""


def _extract_usage(chunk: Any) -> dict[str, int]:
    usage = _lookup(chunk, "usage")
    if not isinstance(usage, Mapping):
        return {}
    normalized: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            normalized[key] = value
    return normalized


def _extract_text_part(item: Any) -> str:
    if isinstance(item, str):
        return item
    text = _lookup(item, "text")
    if isinstance(text, str):
        return text
    return ""


def _extract_tool_call_arguments(tool_calls: Any) -> str:
    if not isinstance(tool_calls, Sequence):
        return ""
    parts: list[str] = []
    for tool_call in tool_calls:
        function_block = _lookup(tool_call, "function")
        arguments = _lookup(function_block, "arguments")
        if isinstance(arguments, str) and arguments.strip():
            parts.append(arguments.strip())
    return "".join(parts)


def _lookup(source: Any, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)
