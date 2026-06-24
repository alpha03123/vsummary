"""基于 LiteLLM 原生联网搜索能力的轻量网关。

把"用户问题 → 联网搜索 → 提取可引用 URL + 摘要"的链路封装为一个同步入口，
供上层 RAG/Web 检索节点直接调用；不做结果缓存、并发或 SSE 进度推送。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.shared.llm.base_url import resolve_openai_compatible_api_base_url


class LiteLLMNativeWebSearchGateway:
    """LiteLLM 联网搜索同步网关。

    业务场景：系列级问答的 `optional_web_search` 节点需要为用户问题补充
    公网信息；本网关调用 LiteLLM 的原生联网能力（`web_search_options`），
    再从响应 `annotations` 中抽出 URL citations。

    实现要点：
    - 模型组装：传入的 `model` 若不包含 `provider/` 前缀会按 `provider`
      拼接，便于适配 OpenAI 兼容网关；
    - 提示词构造：固定中文 prompt，要求"简洁中文概括 + 必须可引用"；
    - 输出解析：优先从 `message.annotations[*].url_citation` 抽取
      `{title, url, text, snippet}`；缺失时退回整段 `content`；
    - 错误处理：缺少 API Key/模型名/provider 时构造期就抛错；搜索结果
      没有任何可引用 URL 时抛 `RuntimeError`；
    - 配置：温度固定 0；`search_context_size` 默认 `medium`；超时由调用方
      通过 `timeout_seconds` 传入；
    - 可测试性：`completion_fn` 允许在测试中替换为假实现。
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        search_context_size: str,
        completion_fn=None,
    ) -> None:
        """校验必要配置并组装 LiteLLM 调用所需的最终参数。

        Args:
            provider: 模型提供方（如 `openai`），最终会作为 `model` 前缀。
            model: 模型名称；不含 `/` 时会自动拼接 `provider/`。
            base_url: OpenAI 兼容 API 根地址，会经过 URL 规范化。
            api_key: API Key；为空时抛 `RuntimeError`。
            search_context_size: 联网搜索上下文深度（low/medium/high），
                为空时退化为 `medium`。
            completion_fn: 可选的可调用对象；为 `None` 时使用 LiteLLM 的
                `completion` 函数，便于在测试中替换。

        Raises:
            RuntimeError: API Key / 模型名称 / provider 任一缺失时抛出。
        """
        normalized_api_key = api_key.strip()
        if not normalized_api_key:
            raise RuntimeError("缺少 API Key，无法调用联网搜索。")
        normalized_model = model.strip()
        if not normalized_model:
            raise RuntimeError("缺少模型名称，无法调用联网搜索。")

        normalized_provider = provider.strip().lower()
        if not normalized_provider:
            raise RuntimeError("缺少模型类型，无法调用联网搜索。")
        self._model = normalized_model if "/" in normalized_model else f"{normalized_provider}/{normalized_model}"
        self._base_url = resolve_openai_compatible_api_base_url(base_url)
        self._api_key = normalized_api_key
        self._search_context_size = search_context_size.strip() or "medium"
        self._completion = completion_fn or _load_litellm_completion()

    def search(self, query: str, *, max_results: int, timeout_seconds: int) -> list[dict[str, object]]:
        """执行一次联网搜索并返回可引用结果列表。

        Args:
            query: 用户原始查询；为空或仅含空白时抛 `ValueError`。
            max_results: 最多返回多少条结果。
            timeout_seconds: LiteLLM 调用的超时秒数。

        Returns:
            每条形如 `{"title", "url", "text", "snippet"}` 的字典列表，
            长度不超过 `max_results`；URL 已按出现顺序去重。

        Raises:
            ValueError: 查询为空时抛出。
            RuntimeError: LiteLLM 缺失或搜索未返回任何可引用来源时抛出。
        """
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("联网搜索 query 不能为空。")
        response = self._completion(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "请联网搜索并用简洁中文概括与问题最相关的信息。"
                        "必须返回可引用来源。\n\n"
                        f"问题：{normalized_query}"
                    ),
                }
            ],
            api_base=self._base_url,
            api_key=self._api_key,
            temperature=0,
            timeout=timeout_seconds,
            web_search_options={
                "search_context_size": self._search_context_size,
            },
        )
        content = _extract_message_content(response)
        results = _extract_url_citations(response, fallback_text=content)
        if not results:
            raise RuntimeError("联网搜索未返回可引用来源。")
        return results[:max_results]


def _load_litellm_completion():
    """惰性加载 LiteLLM `completion` 函数。

    把 `import` 放在函数内部避免模块导入期就强制依赖 LiteLLM。

    Returns:
        LiteLLM 的 `completion` 函数。

    Raises:
        RuntimeError: LiteLLM 未安装时抛出。
    """
    try:
        from litellm import completion
    except ModuleNotFoundError as error:
        raise RuntimeError("缺少 litellm 依赖，无法调用联网搜索。") from error
    return completion


def _extract_message_content(response: Any) -> str:
    """从 LiteLLM 响应中提取首条 choice 的 `message.content` 文本。

    兼容 `Mapping` 与普通对象两种形态；找不到或非字符串则返回空串。

    Args:
        response: LiteLLM `completion` 的返回值。

    Returns:
        去除首尾空白后的文本；无内容时为空串。
    """
    choices = _lookup(response, "choices")
    if not isinstance(choices, Sequence) or not choices:
        return ""
    message = _lookup(choices[0], "message")
    content = _lookup(message, "content")
    if isinstance(content, str):
        return content.strip()
    return ""


def _extract_url_citations(response: Any, *, fallback_text: str) -> list[dict[str, object]]:
    """从响应的 `annotations[*].url_citation` 中抽取可引用结果。

    抽取过程中会按 URL 去重；引用区间（`start_index`/`end_index`）有效时
    截取对应片段作为 `text`/`snippet`，无效则退回到整段 `content`。

    Args:
        response: LiteLLM `completion` 的返回值。
        fallback_text: 当引用区间缺失时使用的兜底文本（通常是整段 content）。

    Returns:
        按出现顺序去重后的结果列表，每条形如
        `{"title", "url", "text", "snippet"}`。
    """
    choices = _lookup(response, "choices")
    if not isinstance(choices, Sequence) or not choices:
        return []
    message = _lookup(choices[0], "message")
    annotations = _lookup(message, "annotations")
    if not isinstance(annotations, Sequence):
        return []

    results: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for annotation in annotations:
        url_citation = _lookup(annotation, "url_citation")
        if url_citation is None:
            continue
        url = _as_str(_lookup(url_citation, "url"))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        title = _as_str(_lookup(url_citation, "title")) or url
        cited_text = _slice_text(
            fallback_text,
            start=_lookup(url_citation, "start_index"),
            end=_lookup(url_citation, "end_index"),
        )
        results.append(
            {
                "title": title,
                "url": url,
                "text": cited_text or fallback_text,
                "snippet": cited_text or fallback_text,
            }
        )
    return results


def _slice_text(text: str, *, start: object, end: object) -> str:
    """按 `start_index` / `end_index` 切片；任一参数非整数或区间非法时返回空串。"""
    if not isinstance(start, int) or not isinstance(end, int):
        return ""
    if start < 0 or end <= start:
        return ""
    return text[start:end].strip()


def _as_str(value: object) -> str:
    """把任意值安全地转成去除首尾空白的字符串，非字符串返回空串。"""
    return value.strip() if isinstance(value, str) else ""


def _lookup(source: Any, key: str) -> Any:
    """同时兼容 `Mapping` 与普通对象的字段读取。"""
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)
