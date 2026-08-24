"""基于 LiteLLM 的思维导图生成适配器。

把 `MindmapGenerator` 端口绑定到 LiteLLM 入口：使用总结数据 + 视频元信息
构造中文提示词，调用 LLM 输出非递归的节点表，再还原为前端使用的树结构。
"""

from __future__ import annotations

import json
from typing import Literal

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.generation.ports import MindmapGenerator
from backend.video_summary.infrastructure.llm.prompts import MINDMAP_PROMPT_TEMPLATE
from backend.video_summary.generation import FlatMindmapPayload, MindmapNodePayload


MindmapOutputEncoding = Literal["tree", "flat"]


class LiteLLMMindmapGenerator(MindmapGenerator):
    """通过 LiteLLM 异步调用 LLM 生成思维导图的实现。

    业务场景：在单视频生成流程结束后，基于已生成的 `summary_data` 让 LLM
    提炼出层级化的思维导图节点/边数据，供前端可视化展示。

    实现要点：
    - 提示词构造：把 `title` / `duration_seconds` / `summary_data`（JSON）
      注入到 `MINDMAP_PROMPT_TEMPLATE` 模板；
    - 输出约束：使用非递归 `FlatMindmapPayload` Pydantic schema 强制 LLM 输出结构，
      失败时由 `LiteLLMCompletionGateway` 自动重试最多 3 次；
    - 错误处理：LLM 解析失败、网关超时等异常由网关层抛出，本适配器
      不做静默兜底。
    """

    def __init__(
        self,
        gateway: LiteLLMCompletionGateway,
        *,
        output_encoding: MindmapOutputEncoding = "flat",
    ) -> None:
        """注入 LiteLLM 网关实例。

        Args:
            gateway: 提供 `acomplete_structured` 能力的 LLM 网关。
        """
        if output_encoding not in {"tree", "flat"}:
            raise ValueError(f"Unsupported mindmap output encoding: {output_encoding}")
        self._gateway = gateway
        self._output_encoding = output_encoding

    async def generate(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
        transcript_text: str = "",
        max_depth: int | None = None,
    ) -> dict[str, object]:
        """生成一次思维导图节点/边字典。

        Args:
            title: 视频标题，用于在提示词中给 LLM 上下文。
            duration_seconds: 视频时长（秒），仅取整后传入提示词。
            summary_data: 已生成的总结数据字典，会被 JSON 序列化后注入提示词。
            transcript_text: 转写文本，截断后注入提示词以提供更多细节。

        Returns:
            `MindmapNodePayload.model_dump()` 的纯字典结果，便于跨层传输
            与持久化。

        Raises:
            RuntimeError: LLM 返回无法通过 schema 校验且重试仍失败时抛出。
        """
        prompt = build_mindmap_prompt(
            title=title,
            duration_seconds=duration_seconds,
            summary_data=summary_data,
            transcript_text=transcript_text,
            output_encoding=self._output_encoding,
            max_depth=max_depth,
        )
        response_model = FlatMindmapPayload if self._output_encoding == "flat" else MindmapNodePayload
        payload = await self._gateway.acomplete_structured(
            [{"role": "user", "content": prompt}],
            response_model=response_model,
            retries=3,
            timeout=120,
        )
        if isinstance(payload, FlatMindmapPayload):
            return payload.to_tree().model_dump()
        return payload.model_dump()


def build_mindmap_prompt(
    *,
    title: str,
    duration_seconds: float,
    summary_data: dict[str, object],
    transcript_text: str = "",
    output_encoding: MindmapOutputEncoding = "flat",
    max_depth: int | None = None,
) -> str:
    """渲染思维导图提示词模板。

    Args:
        title: 视频标题。
        duration_seconds: 视频时长（秒），在模板中取整展示。
        summary_data: 总结数据字典，使用 ensure_ascii=False 以保留中文。
        transcript_text: 转写文本，截断到前 3000 字符以防撑爆上下文窗口。

    Returns:
        渲染完成的提示词字符串。
    """
    truncated = transcript_text[:3000] if transcript_text else ""
    prompt = MINDMAP_PROMPT_TEMPLATE.format(
        title=title,
        duration_seconds=int(duration_seconds),
        summary_json=json.dumps(summary_data, ensure_ascii=False, indent=2),
        transcript_text=truncated,
    )
    if max_depth is not None:
        _validate_max_depth(max_depth)
        prompt = (
            f"{prompt}\n"
            f"本次导图应尽可能使用 {max_depth} 层（根节点为第 1 层），不得超过该层数。"
            "仅在内容不足时允许少于该层数，不要为凑层级添加空泛节点。\n"
        )
    if output_encoding == "flat":
        return (
            f"{prompt}\n"
            "输出格式使用非递归节点表：顶层必须包含 root_id 和 nodes。"
            "nodes 中每项必须包含 id、parent_id、title、summary、start_seconds、end_seconds。"
            "根节点的 parent_id 必须为 null；其它节点的 parent_id 必须是其父节点 id。"
            "不要输出 children 字段。\n"
        )
    return prompt


def _validate_max_depth(max_depth: int) -> None:
    if not 2 <= max_depth <= 5:
        raise ValueError("思维导图最大层级必须在 2 到 5 之间。")
