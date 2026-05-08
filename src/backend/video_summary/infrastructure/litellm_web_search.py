from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.shared.llm.base_url import resolve_openai_compatible_api_base_url


class LiteLLMNativeWebSearchGateway:
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
        normalized_api_key = api_key.strip()
        if not normalized_api_key:
            raise RuntimeError("缺少 API Key，无法调用联网搜索。")
        if provider.strip() != "openai_compatible":
            raise RuntimeError(f"unsupported web search provider '{provider}'")
        normalized_model = model.strip()
        if not normalized_model:
            raise RuntimeError("缺少模型名称，无法调用联网搜索。")

        self._model = normalized_model if "/" in normalized_model else f"openai/{normalized_model}"
        self._base_url = resolve_openai_compatible_api_base_url(base_url)
        self._api_key = normalized_api_key
        self._search_context_size = search_context_size.strip() or "medium"
        self._completion = completion_fn or _load_litellm_completion()

    def search(self, query: str, *, max_results: int, timeout_seconds: int) -> list[dict[str, object]]:
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
    try:
        from litellm import completion
    except ModuleNotFoundError as error:
        raise RuntimeError("缺少 litellm 依赖，无法调用联网搜索。") from error
    return completion


def _extract_message_content(response: Any) -> str:
    choices = _lookup(response, "choices")
    if not isinstance(choices, Sequence) or not choices:
        return ""
    message = _lookup(choices[0], "message")
    content = _lookup(message, "content")
    if isinstance(content, str):
        return content.strip()
    return ""


def _extract_url_citations(response: Any, *, fallback_text: str) -> list[dict[str, object]]:
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
    if not isinstance(start, int) or not isinstance(end, int):
        return ""
    if start < 0 or end <= start:
        return ""
    return text[start:end].strip()


def _as_str(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _lookup(source: Any, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)
