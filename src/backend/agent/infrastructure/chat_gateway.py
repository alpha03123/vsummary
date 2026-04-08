from __future__ import annotations

from collections.abc import Iterator

from backend.agent.ports import ChatGateway, StructuredResponseT
from backend.agent.schemas.messages import AgentChatMessage
from backend.shared.llm import LiteLLMCompletionGateway


class LiteLLMChatGateway(ChatGateway):
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        completion_fn=None,
        acompletion_fn=None,
    ) -> None:
        try:
            self._gateway = LiteLLMCompletionGateway(
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=api_key,
                completion_fn=completion_fn,
                acompletion_fn=acompletion_fn,
            )
        except RuntimeError as error:
            if str(error) == "缺少 API Key，无法调用模型。":
                raise RuntimeError("缺少 API Key，无法调用 Agent 模型。") from error
            raise

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        return self._gateway.complete_text(_dump_messages(messages))

    def create_text_completion_stream(self, messages: list[AgentChatMessage]) -> Iterator[str]:
        return self._gateway.stream_text(_dump_messages(messages))

    def create_structured_completion(
        self,
        messages: list[AgentChatMessage],
        response_model: type[StructuredResponseT],
    ) -> StructuredResponseT:
        return self._gateway.complete_structured(
            _dump_messages(messages),
            response_model=response_model,
        )


def _dump_messages(messages: list[AgentChatMessage]) -> list[dict[str, object]]:
    return [message.model_dump() for message in messages]
