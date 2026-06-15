"""chat 补全流式响应的数据载体。

定义 LiteLLM 流式调用的最小粒度数据块，供 gateway 层在流式迭代中产出。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChatCompletionStreamChunk:
    """流式补全的单个数据块（不可变）。

    同时承载增量文本（``delta``）和可选的 token 用量信息（``usage``）；
    ``usage`` 仅出现在流的最后一个块中，其余块的 ``usage`` 为空字典。

    关键不变量：实例创建后不可修改（frozen=True）。
    """

    delta: str = ""
    usage: dict[str, int] = field(default_factory=dict)
