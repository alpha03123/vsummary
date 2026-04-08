from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from backend.agent.ports import ChatGateway, StructuredResponseT
from backend.agent.schemas.messages import AgentChatMessage


CompletionFn = Callable[..., Any]


class LiteLLMChatGateway(ChatGateway):
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        normalized_api_key = api_key.strip()
        if not normalized_api_key:
            raise RuntimeError("缺少 API Key，无法调用 Agent 模型。")

        self._provider = provider.strip()
        self._model = _normalize_litellm_model(self._provider, model)
        self._base_url = base_url.rstrip("/")
        self._api_key = normalized_api_key
        self._completion = completion_fn or _load_litellm_completion()

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        response = self._completion(
            model=self._model,
            messages=_dump_messages(messages),
            api_base=self._base_url,
            api_key=self._api_key,
            temperature=0,
        )
        content = _extract_completion_content(response)
        if content.strip():
            return content.strip()
        fallback_chunks = list(self.create_text_completion_stream(messages))
        fallback_content = "".join(fallback_chunks).strip()
        if fallback_content:
            return fallback_content
        raise RuntimeError("Agent 返回缺少 message.content。")

    def create_text_completion_stream(self, messages: list[AgentChatMessage]) -> Iterator[str]:
        stream = self._completion(
            model=self._model,
            messages=_dump_messages(messages),
            api_base=self._base_url,
            api_key=self._api_key,
            temperature=0,
            stream=True,
        )
        for chunk in stream:
            delta = _extract_stream_delta(chunk)
            if delta:
                yield delta

    def create_structured_completion(
        self,
        messages: list[AgentChatMessage],
        response_model: type[StructuredResponseT],
    ) -> StructuredResponseT:
        del messages, response_model
        raise RuntimeError("LiteLLM gateway 暂不支持 structured completion，请改走文本/JSON 协议。")


def _load_litellm_completion() -> CompletionFn:
    try:
        from litellm import completion
    except ModuleNotFoundError as error:
        raise RuntimeError("缺少 litellm 依赖，无法调用 Agent 模型。") from error
    return completion


def _normalize_litellm_model(provider: str, model: str) -> str:
    normalized_model = model.strip()
    if not normalized_model:
        raise RuntimeError("缺少模型名称，无法调用 Agent 模型。")
    if provider != "openai_compatible":
        raise RuntimeError(f"unsupported llm provider '{provider}'")
    if "/" in normalized_model:
        return normalized_model
    return f"openai/{normalized_model}"


def _dump_messages(messages: Sequence[AgentChatMessage]) -> list[dict[str, Any]]:
    return [message.model_dump() for message in messages]


def _extract_completion_content(response: Any) -> str:
    choices = _lookup(response, "choices")
    if not isinstance(choices, Sequence) or not choices:
        return ""
    message = _lookup(choices[0], "message")
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
    content = _lookup(delta, "content")
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        parts = [part for part in (_extract_text_part(item) for item in content) if part]
        return "".join(parts)
    return ""


def _extract_text_part(item: Any) -> str:
    if isinstance(item, str):
        return item
    text = _lookup(item, "text")
    if isinstance(text, str):
        return text
    return ""


def _lookup(source: Any, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)
