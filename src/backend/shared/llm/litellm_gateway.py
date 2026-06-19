"""LiteLLM 模型调用网关——vsummary 中所有 LLM 调用的唯一入口。

本模块把 ``litellm.completion`` / ``litellm.acompletion`` 封装为统一的
``LiteLLMCompletionGateway``，对外提供：

* 同步/异步的纯文本补全与流式补全；
* 结构化输出（Pydantic schema → json_object → prompt 三级降级协商）；
* OPENAI_BASE_URL 自动归一化（``{origin}/v1``）；
* reasoning_effort 支持与错误识别；
* 连接测试（``test_connection``）。

网关在初始化时完成所有模型名/密钥/base URL 的校验与归一化，
之后的每次调用只需传 messages 与可选参数。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
import hashlib
import json
from threading import Lock
from typing import Any, TypeVar

from pydantic import BaseModel

from backend.shared.llm.chat_stream import ChatCompletionStreamChunk
from backend.shared.llm.base_url import resolve_provider_api_base_url
from backend.shared.llm.json_mode import describe_validation_error, validate_json_response


StructuredResponseT = TypeVar("StructuredResponseT", bound=BaseModel)
CompletionFn = Callable[..., Any]
AsyncCompletionFn = Callable[..., Awaitable[Any]]
StructuredModeName = str
StructuredMode = tuple[StructuredModeName, list[dict[str, Any]], dict[str, Any] | type[BaseModel] | None]
STRUCTURED_MODE_SCHEMA = "schema"
STRUCTURED_MODE_JSON_OBJECT = "json_object"
STRUCTURED_MODE_PROMPT = "prompt"
STRUCTURED_RESPONSE_FORMAT_ERROR_MARKERS = (
    "response_format",
    "json_schema",
    "json_object",
    "schema is not supported",
    "not support schema",
)
_STRUCTURED_MODE_CACHE: dict[str, StructuredModeName] = {}
_STRUCTURED_MODE_CACHE_LOCK = Lock()


class LiteLLMCompletionGateway:
    """LiteLLM 网关——vsummary 中所有 LLM 调用的唯一入口。

    业务意图：把 ``litellm`` 库的调用的细节（模型名归一化、base URL 归一化、
    结构化输出降级策略、reasoning_effort 校验、响应内容提取）封装在单一类中，
    高层用例只需传入 messages 即可获得文本/结构化/流式结果。

    URL 归一化流程：
    1. 调用 ``resolve_openai_compatible_api_base_url`` 剥离尾部端点；
    2. 确保路径以 ``/v1`` 结尾（已包含版本号则不再追加）；
    3. 最终存入 ``self._base_url`` 供每次调用使用。

    结构化输出协商（json_schema → json_object → prompt）：
    1. 优先用 Pydantic model 的 JSON Schema 作为 ``response_format``；
    2. 若提供商报错（不支持 schema），回退到 ``{"type": "json_object"}``；
    3. 若仍失败，在提示词中注入 JSON Schema 文本、关闭结构化参数；
    4. 每种模式的协商结果会按 ``(provider, base_url, model, api_key)`` 缓存，
       后续请求直接使用已验证成功的模式。

    reasoning_effort 支持：
    仅当构造参数为非空且非 ``"none"`` 时才注入 ``reasoning_effort`` 参数，
    并设置 ``allowed_openai_params`` 以允许 litellm 透传该参数；
    若 LLM 返回不支持 reasoning_effort 的错误，会捕获并转为中文 RuntimeError。

    关键不变量：实例创建后所有配置冻结，不可变。
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        reasoning_effort: str | None = None,
        completion_fn: CompletionFn | None = None,
        acompletion_fn: AsyncCompletionFn | None = None,
    ) -> None:
        self._provider = provider.strip()
        normalized_api_key = api_key.strip()
        if not normalized_api_key and not _allows_empty_api_key(self._provider):
            raise RuntimeError("缺少 API Key，无法调用模型。")
        self._model = _normalize_litellm_model(self._provider, model)
        self._base_url = resolve_provider_api_base_url(self._provider, base_url)
        self._api_key = normalized_api_key or None
        self._reasoning_effort = _normalize_reasoning_effort(reasoning_effort)
        self._structured_mode_cache_key = _build_structured_mode_cache_key(
            provider=self._provider,
            base_url=self._base_url,
            model=self._model,
            api_key=self._api_key,
        )
        self.cache_identity = "|".join(
            [
                type(self).__module__,
                type(self).__qualname__,
                self._provider,
                self._base_url.rstrip("/"),
                self._model,
                self._reasoning_effort or "",
            ]
        )
        self._completion = completion_fn or _load_litellm_completion()
        self._acompletion = acompletion_fn or _load_litellm_acompletion()

    def complete_text(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0,
        response_format: dict[str, Any] | type[BaseModel] | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """同步纯文本补全，返回模型输出（去除首尾空白）。

        从 ``choices[0].message.content`` 提取文本；若为空白则自动回退到
        同步流式调用再拼接结果。若仍为空则抛出 RuntimeError。

        Args:
            messages: 对话消息列表，每项为 ``{"role": ..., "content": ...}``。
            temperature: 采样温度，默认 0（确定性输出）。
            response_format: 可选的响应格式约束（dict 或 Pydantic model 类）。
            max_tokens: 最大生成 token 数；若为 ``None`` 则由模型决定。
            timeout: 请求超时秒数；若为 ``None`` 则不设超时。

        Returns:
            模型返回的纯文本（已去除首尾空白）。

        Raises:
            RuntimeError: 模型返回缺少 message.content 或不支持 reasoning_effort。
        """
        request = _build_completion_request(
            model=self._model,
            messages=_dump_messages(messages),
            api_base=self._base_url,
            api_key=self._api_key,
            temperature=temperature,
            response_format=response_format,
            max_tokens=max_tokens,
            timeout=timeout,
            reasoning_effort=self._reasoning_effort,
        )
        try:
            response = self._completion(**request)
        except Exception as error:
            if _is_unsupported_reasoning_effort_error(error):
                raise RuntimeError("此模型不支持思考强度。") from error
            raise
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
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """异步纯文本补全，返回模型输出（去除首尾空白）。

        与 ``complete_text`` 的语义一致，但使用 ``litellm.acompletion``；
        若响应内容为空则回退到异步流式调用。

        Args:
            messages: 对话消息列表。
            temperature: 采样温度，默认 0。
            response_format: 可选的响应格式约束。
            max_tokens: 最大生成 token 数。
            timeout: 请求超时秒数。

        Returns:
            模型返回的纯文本（已去除首尾空白）。

        Raises:
            RuntimeError: 模型返回缺少 message.content 或不支持 reasoning_effort。
        """
        request = _build_completion_request(
            model=self._model,
            messages=_dump_messages(messages),
            api_base=self._base_url,
            api_key=self._api_key,
            temperature=temperature,
            response_format=response_format,
            max_tokens=max_tokens,
            timeout=timeout,
            reasoning_effort=self._reasoning_effort,
        )
        try:
            response = await self._acompletion(**request)
        except Exception as error:
            if _is_unsupported_reasoning_effort_error(error):
                raise RuntimeError("此模型不支持思考强度。") from error
            raise
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
        """同步流式补全，逐个产出增量文本片段。

        每次迭代返回一个 delta 字符串（可能为空则跳过）；调用方可用
        ``"".join(iterator)`` 得到完整响应。

        Args:
            messages: 对话消息列表。
            temperature: 采样温度，默认 0。
            response_format: 可选的响应格式约束。

        Yields:
            每个非空增量文本片段（str）。

        Raises:
            RuntimeError: 模型不支持 reasoning_effort。
        """
        try:
            stream = self._completion(
                **_build_stream_request(
                    model=self._model,
                    messages=_dump_messages(messages),
                    api_base=self._base_url,
                    api_key=self._api_key,
                    temperature=temperature,
                    response_format=response_format,
                    reasoning_effort=self._reasoning_effort,
                ),
                stream=True,
            )
        except Exception as error:
            if _is_unsupported_reasoning_effort_error(error):
                raise RuntimeError("此模型不支持思考强度。") from error
            raise
        in_think_block = False
        for chunk in stream:
            reasoning_delta, content_delta = _extract_stream_deltas(chunk)
            if reasoning_delta:
                if not in_think_block:
                    yield "<think>"
                    in_think_block = True
                yield reasoning_delta
            if content_delta:
                if in_think_block:
                    yield "</think>"
                    in_think_block = False
                yield content_delta
        if in_think_block:
            yield "</think>"

    def stream_text_with_metadata(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0,
        response_format: dict[str, Any] | type[BaseModel] | None = None,
    ) -> Iterator[ChatCompletionStreamChunk]:
        """同步流式补全，产出带 token 用量元数据的 ``ChatCompletionStreamChunk``。

        与 ``stream_text`` 的区别在于：会开启 ``stream_options={"include_usage": True}``
        并从流中提取 ``usage`` 信息，在流的末尾追加一个仅含 usage 的 chunk。

        Args:
            messages: 对话消息列表。
            temperature: 采样温度，默认 0。
            response_format: 可选的响应格式约束。

        Yields:
            ``ChatCompletionStreamChunk`` 对象：文本增量块或末尾的 usage 块。

        Raises:
            RuntimeError: 模型不支持 reasoning_effort。
        """
        try:
            stream = self._completion(
                **_build_stream_request(
                    model=self._model,
                    messages=_dump_messages(messages),
                    api_base=self._base_url,
                    api_key=self._api_key,
                    temperature=temperature,
                    response_format=response_format,
                    reasoning_effort=self._reasoning_effort,
                ),
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as error:
            if _is_unsupported_reasoning_effort_error(error):
                raise RuntimeError("此模型不支持思考强度。") from error
            raise
        final_usage: dict[str, int] = {}
        in_think_block = False
        for chunk in stream:
            reasoning_delta, delta = _extract_stream_deltas(chunk)
            usage = _extract_usage(chunk)
            if usage:
                final_usage = usage
            if reasoning_delta:
                if not in_think_block:
                    yield ChatCompletionStreamChunk(delta="<think>")
                    in_think_block = True
                yield ChatCompletionStreamChunk(delta=reasoning_delta)
            if delta:
                if in_think_block:
                    yield ChatCompletionStreamChunk(delta="</think>")
                    in_think_block = False
                yield ChatCompletionStreamChunk(delta=delta)
        if in_think_block:
            yield ChatCompletionStreamChunk(delta="</think>")
        if final_usage:
            yield ChatCompletionStreamChunk(usage=final_usage)

    def test_connection(self) -> str:
        """发送一条极简 prompt 以验证 LLM 连接是否畅通。

        发送 ``"Reply with exactly: ok"`` 并要求模型回复 ``ok``；
        超时设为 5 秒，最大 token 数设为 8。

        Returns:
            模型返回的文本（预期为 ``"ok"``）。

        Raises:
            RuntimeError: LLM 连接失败或返回异常。
        """
        return self.complete_text(
            [{"role": "user", "content": "Reply with exactly: ok"}],
            temperature=0,
            max_tokens=8,
            timeout=5,
        )

    async def astream_text(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0,
        response_format: dict[str, Any] | type[BaseModel] | None = None,
    ):
        """异步流式补全，逐个产出增量文本片段。

        与 ``stream_text`` 语义一致但使用 async 迭代；适合在 asyncio
        协程中配合 ``async for`` 使用。

        Args:
            messages: 对话消息列表。
            temperature: 采样温度，默认 0。
            response_format: 可选的响应格式约束。

        Yields:
            每个非空增量文本片段（str）。

        Raises:
            RuntimeError: 模型不支持 reasoning_effort。
        """
        try:
            stream = await self._acompletion(
                **_build_stream_request(
                    model=self._model,
                    messages=_dump_messages(messages),
                    api_base=self._base_url,
                    api_key=self._api_key,
                    temperature=temperature,
                    response_format=response_format,
                    reasoning_effort=self._reasoning_effort,
                ),
                stream=True,
            )
        except Exception as error:
            if _is_unsupported_reasoning_effort_error(error):
                raise RuntimeError("此模型不支持思考强度。") from error
            raise
        in_think_block = False
        async for chunk in stream:
            reasoning_delta, content_delta = _extract_stream_deltas(chunk)
            if reasoning_delta:
                if not in_think_block:
                    yield "<think>"
                    in_think_block = True
                yield reasoning_delta
            if content_delta:
                if in_think_block:
                    yield "</think>"
                    in_think_block = False
                yield content_delta
        if in_think_block:
            yield "</think>"

    def complete_structured(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        response_model: type[StructuredResponseT],
        temperature: float = 0,
        retries: int = 2,
    ) -> StructuredResponseT:
        """同步结构化输出：要求 LLM 返回符合 Pydantic schema 的对象。

        核心流程：
        1. 构建三级降级模式列表（json_schema → json_object → prompt）；
        2. 逐个模式尝试调用 LLM，成功则缓存该模式供后续使用；
        3. 对返回文本调用 ``validate_json_response`` 做 Pydantic 校验；
        4. 校验失败则在下一轮重试的消息中追加校验错误信息。

        Args:
            messages: 对话消息列表。
            response_model: 期望的 Pydantic 模型类。
            temperature: 采样温度，默认 0。
            retries: 最大重试次数（含首次），默认 2 次（共 3 轮）。

        Returns:
            通过校验的 Pydantic 模型实例。

        Raises:
            RuntimeError: 所有 response_format 模式均不可用，或重试耗尽
                后仍校验失败（错误消息中包含原始 LLM 输出）。
        """
        validation_error: str | None = None
        last_raw_text = ""

        for attempt_index in range(retries + 1):
            modes = _build_structured_request_modes(
                cache_key=self._structured_mode_cache_key,
                messages=messages,
                response_model=response_model,
                validation_error=validation_error,
            )
            mode_errors: list[str] = []
            for mode_name, structured_messages, response_format in modes:
                try:
                    last_raw_text = self.complete_text(
                        structured_messages,
                        temperature=temperature,
                        response_format=response_format,
                    )
                    _remember_structured_mode(self._structured_mode_cache_key, mode_name)
                    break
                except Exception as error:
                    if not _is_response_format_error(error) or response_format is None:
                        raise
                    mode_errors.append(str(error))
            else:
                raise RuntimeError(
                    "LiteLLM 结构化请求失败: 所有 response_format 模式均不可用。"
                    f"{'; '.join(mode_errors)}"
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
        """异步结构化输出：要求 LLM 返回符合 Pydantic schema 的对象。

        与 ``complete_structured`` 语义一致，但使用 ``acomplete_text``
        做底层 LLM 调用；适合在 asyncio 协程中并发使用。

        Args:
            messages: 对话消息列表。
            response_model: 期望的 Pydantic 模型类。
            temperature: 采样温度，默认 0。
            retries: 最大重试次数（含首次），默认 2 次。

        Returns:
            通过校验的 Pydantic 模型实例。

        Raises:
            RuntimeError: 所有 response_format 模式均不可用，或重试耗尽
                后仍校验失败。
        """
        validation_error: str | None = None
        last_raw_text = ""

        for attempt_index in range(retries + 1):
            modes = _build_structured_request_modes(
                cache_key=self._structured_mode_cache_key,
                messages=messages,
                response_model=response_model,
                validation_error=validation_error,
            )
            mode_errors: list[str] = []
            for mode_name, structured_messages, response_format in modes:
                try:
                    last_raw_text = await self.acomplete_text(
                        structured_messages,
                        temperature=temperature,
                        response_format=response_format,
                    )
                    _remember_structured_mode(self._structured_mode_cache_key, mode_name)
                    break
                except Exception as error:
                    if not _is_response_format_error(error) or response_format is None:
                        raise
                    mode_errors.append(str(error))
            else:
                raise RuntimeError(
                    "LiteLLM 结构化请求失败: 所有 response_format 模式均不可用。"
                    f"{'; '.join(mode_errors)}"
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
    """尝试导入 ``litellm.completion``，失败时抛出中文 RuntimeError。

    Returns:
        ``litellm.completion`` 函数引用。

    Raises:
        RuntimeError: litellm 包未安装。
    """
    try:
        from litellm import completion
    except ModuleNotFoundError as error:
        raise RuntimeError("缺少 litellm 依赖，无法调用模型。") from error
    return completion


def _load_litellm_acompletion() -> AsyncCompletionFn:
    """尝试导入 ``litellm.acompletion``（异步版本），失败时抛出中文 RuntimeError。

    Returns:
        ``litellm.acompletion`` 函数引用。

    Raises:
        RuntimeError: litellm 包未安装。
    """
    try:
        from litellm import acompletion
    except ModuleNotFoundError as error:
        raise RuntimeError("缺少 litellm 依赖，无法调用模型。") from error
    return acompletion


def _normalize_litellm_model(provider: str, model: str) -> str:
    """将 provider 与 model 组合为 litellm 所期望的 ``provider/model`` 格式。

    若 model 已包含 ``/``（如 ``openai/gpt-4o``）则直接使用；
    否则拼接为 ``{provider}/{model}``。

    Args:
        provider: 提供商名称（如 ``"openai"``）。
        model: 模型名称（如 ``"gpt-4o"``）。

    Returns:
        ``"provider/model"`` 格式的归一化字符串。

    Raises:
        RuntimeError: provider 或 model 为空。
    """
    normalized_model = model.strip()
    if not normalized_model:
        raise RuntimeError("缺少模型名称，无法调用模型。")
    if "/" in normalized_model:
        return normalized_model
    normalized_provider = provider.strip().lower()
    if not normalized_provider:
        raise RuntimeError("缺少模型类型，无法调用模型。")
    return f"{normalized_provider}/{normalized_model}"


def _allows_empty_api_key(provider: str) -> bool:
    return provider.strip().lower() == "ollama"


def _dump_messages(messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """将消息序列浅拷贝为普通 list，供 litellm 参数化使用。

    Args:
        messages: 对话消息序列。

    Returns:
        浅拷贝后的消息列表。
    """
    return [dict(message) for message in messages]


def _build_completion_request(
    *,
    model: str,
    messages: list[dict[str, Any]],
    api_base: str,
    api_key: str | None,
    temperature: float,
    response_format: dict[str, Any] | type[BaseModel] | None,
    max_tokens: int | None,
    timeout: float | None,
    reasoning_effort: str | None,
) -> dict[str, Any]:
    """构建 litellm completion 调用所需的请求参数字典。

    会自动跳过 ``None`` 的可选参数（``max_tokens``、``timeout``、
    ``reasoning_effort``）；若 reasoning_effort 不为空则设置
    ``allowed_openai_params`` 以允许 litellm 透传该参数。

    Args:
        model: 归一化后的模型名。
        messages: 对话消息列表。
        api_base: 归一化后的 API base URL。
        api_key: API 密钥。
        temperature: 采样温度。
        response_format: 可选的响应格式约束。
        max_tokens: 最大生成 token 数；若为 ``None`` 则省略该参数。
        timeout: 请求超时秒数；若为 ``None`` 则省略该参数。
        reasoning_effort: 思考强度；若为 ``None`` 则省略。

    Returns:
        litellm ``completion(**kwargs)`` 可直接使用的参数字典。
    """
    request: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "api_key": api_key,
        "temperature": temperature,
        "response_format": response_format,
    }
    if api_base:
        request["api_base"] = api_base
    if max_tokens is not None:
        request["max_tokens"] = max_tokens
    if timeout is not None:
        request["timeout"] = timeout
    if reasoning_effort is not None:
        request["reasoning_effort"] = reasoning_effort
        request["allowed_openai_params"] = ["reasoning_effort"]
    return request


def _build_stream_request(
    *,
    model: str,
    messages: list[dict[str, Any]],
    api_base: str,
    api_key: str,
    temperature: float,
    response_format: dict[str, Any] | type[BaseModel] | None,
    reasoning_effort: str | None,
) -> dict[str, Any]:
    """构建 litellm 流式 completion 调用的请求参数字典。

    与 ``_build_completion_request`` 的区别在于：不含 ``max_tokens`` 与
    ``timeout`` 参数（流式调用不需要这两个字段）。

    Args:
        model: 归一化后的模型名。
        messages: 对话消息列表。
        api_base: 归一化后的 API base URL。
        api_key: API 密钥。
        temperature: 采样温度。
        response_format: 可选的响应格式约束。
        reasoning_effort: 思考强度；若为 ``None`` 则省略。

    Returns:
        可用于 ``completion(**kwargs, stream=True)`` 的参数字典。
    """
    request: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "api_key": api_key,
        "temperature": temperature,
        "response_format": response_format,
    }
    if api_base:
        request["api_base"] = api_base
    if reasoning_effort is not None:
        request["reasoning_effort"] = reasoning_effort
        request["allowed_openai_params"] = ["reasoning_effort"]
    return request


def _normalize_reasoning_effort(value: str | None) -> str | None:
    """校验并归一化 reasoning_effort 参数。

    仅接受 ``"low"``、``"medium"``、``"high"`` 三个有效值；
    ``None``、空字符串或 ``"none"`` 统一返回 ``None``（不启用思考强度）。

    Args:
        value: 用户配置的 reasoning_effort 字符串。

    Returns:
        小写的有效值字符串或 ``None``。

    Raises:
        RuntimeError: 传入的值不在合法范围内。
    """
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized == "none":
        return None
    if normalized not in {"low", "medium", "high"}:
        raise RuntimeError(f"unsupported reasoning_effort '{value}'")
    return normalized


def _is_unsupported_reasoning_effort_error(error: Exception) -> bool:
    """判断异常是否因模型不支持 reasoning_effort 引起。

    通过检查异常消息中是否同时包含 ``"reasoning_effort"`` 和
    ``"unsupported"`` / ``"not support"`` 等关键词来判断。

    Args:
        error: 捕获的异常对象。

    Returns:
        若错误与不受支持的 reasoning_effort 相关则返回 ``True``。
    """
    message = str(error).lower()
    return "reasoning_effort" in message and (
        "unsupported" in message
        or "does not support" in message
        or "not support" in message
        or "unsupportedparams" in message
    )


def _build_structured_request_modes(
    *,
    cache_key: str,
    messages: Sequence[dict[str, Any]],
    response_model: type[BaseModel],
    validation_error: str | None,
) -> list[StructuredMode]:
    """构建结构化输出的三级降级模式列表。

    生成本次请求需要用到的全部模式（json_schema → json_object → prompt），
    按优先级排序；若已有缓存的成功模式，将其提升到列表首位以跳过不必要的降级尝试。

    Args:
        cache_key: 用于查询缓存的键（由 provider/base_url/model/api_key 生成）。
        messages: 原始对话消息。
        response_model: 期望的 Pydantic 模型类。
        validation_error: 上一次校验失败的错误信息（重试时追加到消息末尾）；
            若为 ``None`` 则说明是首次尝试。

    Returns:
        ``(模式名, 处理后消息, response_format)`` 元组列表，按尝试顺序排列。
    """
    modes = [
        (
            STRUCTURED_MODE_SCHEMA,
            _append_validation_retry_messages(messages, validation_error),
            response_model,
        ),
        (
            STRUCTURED_MODE_JSON_OBJECT,
            _build_json_mode_messages(messages=messages, validation_error=validation_error),
            {"type": "json_object"},
        ),
        (
            STRUCTURED_MODE_PROMPT,
            _build_prompt_fallback_messages(
                messages=messages,
                response_model=response_model,
                validation_error=validation_error,
            ),
            None,
        ),
    ]
    cached_mode = _lookup_structured_mode(cache_key)
    if cached_mode is None:
        return modes
    selected = [mode for mode in modes if mode[0] == cached_mode]
    if not selected:
        return modes
    remaining = [mode for mode in modes if mode[0] != cached_mode]
    return [*selected, *remaining]


def _build_json_mode_messages(
    *,
    messages: Sequence[dict[str, Any]],
    validation_error: str | None,
) -> list[dict[str, Any]]:
    """为 json_object 模式构造消息列表。

    在原始消息前插入一条角色为 ``user`` 的指令，要求 LLM 只输出 JSON
    对象且不附加 Markdown/代码块/额外文本；若为校验失败后的重试，则在末尾
    追加一条校验错误提示消息。

    Args:
        messages: 原始对话消息。
        validation_error: 上一轮的校验错误（重试时使用）；若为 ``None`` 则
            不追加错误提示。

    Returns:
        处理后的消息列表，可直接传入 completion 调用。
    """
    structured_messages = [
        {
            "role": "user",
            "content": "这是 JSON mode 请求。只输出一个 JSON 对象，不要输出 Markdown、解释、代码块或额外文本。",
        },
        *_dump_messages(messages),
    ]
    if validation_error:
        structured_messages.append(_build_validation_retry_message(validation_error))
    return structured_messages


def _build_prompt_fallback_messages(
    *,
    messages: Sequence[dict[str, Any]],
    response_model: type[BaseModel],
    validation_error: str | None,
) -> list[dict[str, Any]]:
    """为 prompt 降级模式构造消息列表。

    在原始消息前插入一条指令，其中包含 ``response_model`` 的 JSON Schema
    全文，让不支持结构化输出的 LLM 也能按 Schema 生成 JSON；
    ``response_format`` 参数将被设为 ``None``。

    Args:
        messages: 原始对话消息。
        response_model: 期望的 Pydantic 模型类（用于生成 Schema 文本）。
        validation_error: 上一轮的校验错误信息（重试时追加）。

    Returns:
        处理后的消息列表，其中第一条 user 消息包含 JSON Schema 指令。
    """
    schema = response_model.model_json_schema()
    instruction = (
        "这是结构化输出请求。只输出一个 JSON 对象，不要输出 Markdown、解释、代码块、引用清单或额外文本。\n"
        f"JSON 对象必须匹配 {response_model.__name__} 的 JSON Schema：\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )
    structured_messages = [
        {
            "role": "user",
            "content": instruction,
        },
        *_dump_messages(messages),
    ]
    if validation_error:
        structured_messages.append(_build_validation_retry_message(validation_error))
    return structured_messages


def _append_validation_retry_messages(
    messages: Sequence[dict[str, Any]],
    validation_error: str | None,
) -> list[dict[str, Any]]:
    """为 json_schema 模式的校验重试追加错误提示消息。

    json_schema 模式不需要重写前置指令，只需在原始消息末尾追加校验
    错误的提示即可。

    Args:
        messages: 原始对话消息。
        validation_error: 校验错误信息；若为 ``None`` 则不做任何追加。

    Returns:
        处理后的消息列表。
    """
    structured_messages = _dump_messages(messages)
    if validation_error:
        structured_messages.append(_build_validation_retry_message(validation_error))
    return structured_messages


def _build_validation_retry_message(validation_error: str) -> dict[str, str]:
    """构造一条 user 角色的校验重试提示消息。

    告知 LLM 上一轮输出未通过本地校验，并附上校验错误详情；
    要求模型修正后仅输出一个 JSON 对象。

    Args:
        validation_error: 校验失败的错误描述。

    Returns:
        形如 ``{"role": "user", "content": "..."}`` 的重试提示消息。
    """
    return {
        "role": "user",
        "content": (
            "上一轮结构化输出没有通过本地校验，请修正后重新输出。\n"
            f"校验错误：{validation_error}\n"
            "仍然只输出一个 JSON 对象，不要输出任何额外文本。"
        ),
    }


def _is_response_format_error(error: Exception) -> bool:
    """判断异常是否因 response_format（json_schema/json_object）不受支持。

    通过检查异常消息中是否包含 ``"response_format"``、``"json_schema"``、
    ``"json_object"``、``"schema is not supported"`` 等标记词来判断。

    Args:
        error: 捕获的异常对象。

    Returns:
        若错误与不受支持的 response_format 相关则返回 ``True``。
    """
    text = str(error).lower()
    return any(marker in text for marker in STRUCTURED_RESPONSE_FORMAT_ERROR_MARKERS)


def _build_structured_mode_cache_key(
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
) -> str:
    """基于 provider、base_url、model 与 api_key 生成结构化模式缓存键。

    api_key 使用 SHA-256 哈希的前 12 个十六进制字符代替原文，
    避免在日志/调试输出中泄露密钥。

    Args:
        provider: 提供商名称。
        base_url: 归一化后的 API base URL。
        model: 归一化后的模型名。
        api_key: API 密钥（原文，仅用于哈希）。

    Returns:
        形如 ``"openai|https://api.openai.com/v1|gpt-4o|a1b2c3d4e5f6"`` 的缓存键。
    """
    key_hash = hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()[:12]
    return "|".join([provider.strip(), base_url.rstrip("/"), model.strip(), key_hash])


def _lookup_structured_mode(cache_key: str) -> StructuredModeName | None:
    """线程安全地查询结构化模式缓存。

    Args:
        cache_key: 由 ``_build_structured_mode_cache_key`` 生成的缓存键。

    Returns:
        缓存的成功模式名（如 ``"json_object"``）；若未命中则返回 ``None``。
    """
    with _STRUCTURED_MODE_CACHE_LOCK:
        return _STRUCTURED_MODE_CACHE.get(cache_key)


def _remember_structured_mode(cache_key: str, mode_name: StructuredModeName) -> None:
    """线程安全地将成功的结构化模式写入缓存。

    Args:
        cache_key: 缓存键。
        mode_name: 已验证成功的模式名。
    """
    with _STRUCTURED_MODE_CACHE_LOCK:
        _STRUCTURED_MODE_CACHE[cache_key] = mode_name


def clear_structured_mode_cache() -> None:
    """清空全局结构化模式缓存（供测试环境使用）。"""
    with _STRUCTURED_MODE_CACHE_LOCK:
        _STRUCTURED_MODE_CACHE.clear()


def _extract_completion_content(response: Any) -> str:
    """从 litellm 完成响应中提取文本内容。

    优先级：tool_calls 的 arguments > message.content (str) > content parts 拼接。
    兼容 dict 和对象形式的响应。

    Args:
        response: litellm 返回的完整响应对象（dict 或 object）。

    Returns:
        提取到的文本内容；若无法提取则返回空字符串。
    """
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
    """从 litellm 流式 chunk 中提取增量文本。

    优先级：tool_calls arguments > delta.content (str) > content parts 拼接。

    Args:
        chunk: litellm 流式迭代产出的单个数据块。

    Returns:
        提取到的增量文本；若为空则返回空字符串。
    """
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


def _extract_stream_deltas(chunk: Any) -> tuple[str, str]:
    """从流式 chunk 中分别提取推理增量和回答增量。"""
    choices = _lookup(chunk, "choices")
    if not isinstance(choices, Sequence) or not choices:
        return "", ""
    delta = _lookup(choices[0], "delta")
    reasoning_content = _lookup(delta, "reasoning_content")
    reasoning_delta = reasoning_content if isinstance(reasoning_content, str) else ""
    return reasoning_delta, _extract_stream_delta(chunk)


def _extract_usage(chunk: Any) -> dict[str, int]:
    """从流式 chunk 中提取 token 用量信息。

    提取 ``prompt_tokens``、``completion_tokens``、``total_tokens``
    三个字段（仅当值为 int 时）、忽略非整数值。

    Args:
        chunk: litellm 流式数据块。

    Returns:
        以 token 类别为键的用量字典；若无用量信息则返回空字典。
    """
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
    """从 content parts 数组的单个元素中提取文本。

    兼容纯字符串或含 ``"text"`` 键的 dict/对象两种形态。

    Args:
        item: content parts 数组中的单个元素。

    Returns:
        提取到的文本；无法提取时返回空字符串。
    """
    if isinstance(item, str):
        return item
    text = _lookup(item, "text")
    if isinstance(text, str):
        return text
    return ""


def _extract_tool_call_arguments(tool_calls: Any) -> str:
    """从 tool_calls 数组中提取所有 function arguments 的拼接文本。

    Args:
        tool_calls: ``choices[0].message.tool_calls`` 或
            ``choices[0].delta.tool_calls``（list 形式）。

    Returns:
        所有 arguments 的拼接字符串；无 tool_calls 则返回空字符串。
    """
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
    """兼容 dict 与对象两种形式的属性访问。

    若 source 是 Mapping 则用 ``.get(key)``，否则用 ``getattr(source, key, None)``；
    这样 litellm 返回的 dict/对象响应可以统一处理。

    Args:
        source: 待查询的源对象（dict 或任意对象）。
        key: 要访问的属性名。

    Returns:
        属性值；键不存在时返回 ``None``。
    """
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)
