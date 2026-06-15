"""Agent 层的"LLM 流式分片"模型重导出。

业务意图：Agent 适配器（`LiteLLMChatGateway`）在流式返回时希望使用一个
Agent 视角的类型名；该类型本质就是共享层 LiteLLM 网关的流式分片模型，
为避免在 Agent 与共享层之间出现重复定义，本模块只做重命名导出。
"""

from backend.shared.llm.chat_stream import ChatCompletionStreamChunk

__all__ = ["ChatCompletionStreamChunk"]
