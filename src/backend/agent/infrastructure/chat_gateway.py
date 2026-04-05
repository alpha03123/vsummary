from __future__ import annotations

from collections.abc import Iterator

from pydantic import BaseModel

from backend.agent.ports import ChatGateway, StructuredResponseT
from backend.agent.schemas.messages import AgentChatMessage


class OpenAICompatibleChatGateway:
    def __init__(self, model: str, base_url: str, api_key: str) -> None:
        if not api_key:
            raise RuntimeError("缺少 API Key，无法调用 Agent 模型。")
        try:
            from openai import OpenAI
        except ModuleNotFoundError as error:
            raise RuntimeError("缺少 openai 依赖，无法使用结构化 Agent 网关。") from error
        self._model = model
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
        )

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[message.model_dump() for message in messages],
            temperature=0,
        )
        content = response.choices[0].message.content
        if isinstance(content, str) and content.strip():
            return content.strip()
        raise RuntimeError("Agent 返回缺少 message.content。")

    def create_text_completion_stream(self, messages: list[AgentChatMessage]) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=[message.model_dump() for message in messages],
            temperature=0,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if isinstance(delta, str) and delta:
                yield delta

    def create_structured_completion(
        self,
        messages: list[AgentChatMessage],
        response_model: type[StructuredResponseT],
    ) -> StructuredResponseT:
        response = self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[message.model_dump() for message in messages],
            response_format=response_model,
            temperature=0,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(f"Agent 返回无法解析为 {response_model.__name__}。")
        return parsed
