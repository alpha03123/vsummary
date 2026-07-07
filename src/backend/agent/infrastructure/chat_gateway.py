"""把 Agent 层 `ChatGateway` Port 桥接到 LiteLLM 的适配器实现。

业务意图：让 Agent 核心不直接依赖 LiteLLM SDK，而是通过 Port 接口拿到
`ChatGateway`；本适配器把内部使用的 `AgentChatMessage` 序列化后转发给共享层
的 `LiteLLMCompletionGateway`，并把"缺少 API Key"等底层错误翻译成 Agent
语义的报错。
"""

from __future__ import annotations

from collections.abc import Iterator

from backend.agent.ports import ChatGateway, StructuredResponseT
from backend.agent.schemas.chat_stream import ChatCompletionStreamChunk
from backend.agent.schemas.messages import AgentChatMessage
from backend.shared.llm import LiteLLMCompletionGateway


class LiteLLMChatGateway(ChatGateway):
    """基于 LiteLLM 实现的 Agent `ChatGateway` Port。

    业务场景：Agent 核心（LangGraph 节点、规划器、合成器）只依赖 `ChatGateway`
    Port；本类把"以 `AgentChatMessage` 列表输入、文本/流/结构化 JSON 之一输出"
    的需求统一翻译给 LiteLLM，并把底层异常包装成 Agent 友好文案。

    实现要点：
    - 构造时直接转发配置给共享层 `LiteLLMCompletionGateway`；为支持测试
      注入，底层的 `completion_fn` / `acompletion_fn` 也通过构造参数透传。
    - 把"缺少 API Key"异常重写成"缺少 API Key，无法调用 Agent 模型。"，
      方便前端在 Agent 场景下做差异化提示。
    - 所有 `create_*` 方法内部把 `AgentChatMessage` 通过 `_dump_messages`
      序列化为 LiteLLM 接受的字典列表，再透传给网关。
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        reasoning_effort: str | None = None,
        completion_fn=None,
        acompletion_fn=None,
    ) -> None:
        """注入 LiteLLM 所需配置并构造底层的共享层 LLM 网关。

        Args:
            provider: LiteLLM 兼容的 provider 标识（如 `openai`、`deepseek`）。
            model: 目标模型名。
            base_url: 模型服务的 OpenAI 兼容 base URL。
            api_key: 访问模型服务所需的 API Key。
            reasoning_effort: 可选的推理强度（部分模型支持）。
            completion_fn: 可选的同步 `litellm.completion` 替身，主要用于测试。
            acompletion_fn: 可选的异步 `litellm.acompletion` 替身，主要用于测试。

        Raises:
            RuntimeError: 当底层网关因缺少 API Key 抛错时，重写文案为 Agent 语义。
        """
        try:
            self._gateway = LiteLLMCompletionGateway(
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=api_key,
                reasoning_effort=reasoning_effort,
                completion_fn=completion_fn,
                acompletion_fn=acompletion_fn,
            )
        except RuntimeError as error:
            if str(error) == "缺少 API Key，无法调用模型。":
                raise RuntimeError("缺少 API Key，无法调用 Agent 模型。") from error
            raise

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        """调用 LLM 一次性返回完整文本回答。

        Args:
            messages: Agent 视角的对话消息列表。

        Returns:
            LLM 输出的纯文本。
        """
        return self._gateway.complete_text(_dump_messages(messages))

    def create_text_completion_stream(self, messages: list[AgentChatMessage]) -> Iterator[str]:
        """以增量流式方式返回 LLM 文本 token。

        Args:
            messages: Agent 视角的对话消息列表。

        Returns:
            增量文本片段的迭代器；每个片段为模型输出的一小段字符串。
        """
        return self._gateway.stream_text(_dump_messages(messages))

    def create_text_completion_stream_with_metadata(
        self,
        messages: list[AgentChatMessage],
    ) -> Iterator[ChatCompletionStreamChunk]:
        """以增量流式方式返回 LLM 文本，并附带每个分片的元数据。

        Args:
            messages: Agent 视角的对话消息列表。

        Returns:
            包含元数据（模型名、是否结束、token 用量等）的流式分片迭代器。
        """
        return self._gateway.stream_text_with_metadata(_dump_messages(messages))

    def create_structured_completion(
        self,
        messages: list[AgentChatMessage],
        response_model: type[StructuredResponseT],
    ) -> StructuredResponseT:
        """调用 LLM 并强制输出符合 Pydantic `response_model` 的结构化结果。

        Args:
            messages: Agent 视角的对话消息列表。
            response_model: 用于约束输出与解析结果的目标 Pydantic 类型。

        Returns:
            由 LLM 填充后的 `response_model` 实例。
        """
        return self._gateway.complete_structured(
            _dump_messages(messages),
            response_model=response_model,
        )


def _dump_messages(messages: list[AgentChatMessage]) -> list[dict[str, object]]:
    """把 `AgentChatMessage` 列表序列化为 LiteLLM 接受的字典列表。

    Args:
        messages: Agent 视角的对话消息。

    Returns:
        与 `litellm.completion` / `litellm.acompletion` 兼容的消息字典列表。
    """
    return [message.model_dump() for message in messages]
