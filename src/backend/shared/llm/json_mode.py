"""从 LLM 文本响应中提取并校验 JSON 结构体。

支持三种提取策略：直接 JSON 解析 → Markdown 代码块提取 → 括号平衡扫描；
并可通过 ``require_object=True`` 强制要求顶层为 JSON 对象。
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

def validate_json_response(
    *,
    raw_text: str,
    response_model: type[BaseModel],
) -> BaseModel:
    """从 LLM 原始文本中提取 JSON 对象并用 Pydantic 模型校验。

    组合 ``extract_json_document`` 与 ``response_model.model_validate``
    两步，返回已校验的模型实例。

    Args:
        raw_text: LLM 返回的原始文本。
        response_model: 用于校验的 Pydantic 模型类。

    Returns:
        已校验并实例化的 Pydantic 模型对象。

    Raises:
        ValueError: 无法从文本中提取 JSON 对象。
        ValidationError: JSON 结构与 ``response_model`` 不匹配。
    """
    payload = extract_json_document(raw_text, require_object=True)
    return response_model.model_validate(payload)


def describe_validation_error(error: Exception) -> str:
    """将 Pydantic 校验异常转换为人类可读的中文错误信息。

    Args:
        error: 捕获的异常对象；若为 ``ValidationError`` 则输出字段级
            错误明细（JSON 格式），否则回退到 ``str(error)``。

    Returns:
        描述校验失败原因的错误字符串。
    """
    if isinstance(error, ValidationError):
        return json.dumps(error.errors(include_url=False), ensure_ascii=False)
    return str(error)


def extract_json_document(raw_text: str, *, require_object: bool = False) -> object:
    """从 LLM 原始文本中提取 JSON 值（对象或数组）。

    依次尝试三种策略，命中即返回：

    1. 直接 ``json.loads`` 解析整个文本；
    2. 匹配 Markdown 代码块（`` ```json ``` ``` ``）中的内容；
    3. 在大括号/中括号间做平衡扫描，取匹配区间的 JSON 片段。

    Args:
        raw_text: LLM 返回的原始文本。
        require_object: 若为 ``True`` 则强制要求顶层 JSON 为对象
            （``dict``），否则允许数组。

    Returns:
        解析出的 Python 对象（``dict`` / ``list`` 等）。

    Raises:
        ValueError: 文本为空或未找到可解析的 JSON。
    """
    text = raw_text.strip()
    if not text:
        raise ValueError("模型返回为空，无法解析 JSON。")

    direct_value = _try_json_load(text)
    if direct_value is not None:
        if require_object and not isinstance(direct_value, dict):
            raise ValueError("模型返回的 JSON 顶层必须是对象。")
        return direct_value

    fenced_value = _extract_fenced_json(text, require_object=require_object)
    if fenced_value is not None:
        return fenced_value

    balanced_value = _extract_balanced_json(text, require_object=require_object)
    if balanced_value is not None:
        return balanced_value

    if require_object:
        raise ValueError("模型返回中未找到可解析的 JSON 对象。")
    raise ValueError("模型返回中未找到可解析的 JSON。")


def _try_json_load(candidate: str) -> object | None:
    """安全地尝试 ``json.loads``，失败时返回 ``None`` 而非抛异常。

    Args:
        candidate: 待解析的 JSON 字符串。

    Returns:
        解析成功返回 Python 对象，否则返回 ``None``。
    """
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _extract_fenced_json(text: str, *, require_object: bool = False) -> object | None:
    """从 Markdown 代码块中提取 JSON。

    匹配 `` ```json ``` `` 或 `` ``` ``` `` 围栏内的内容，
    逐个尝试解析直到成功。

    Args:
        text: LLM 返回的原始文本。
        require_object: 若为 ``True`` 则跳过顶层非对象的 JSON。

    Returns:
        解析成功返回 Python 对象，否则返回 ``None``。
    """
    matches = re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    for match in matches:
        candidate = match.group(1).strip()
        loaded = _try_json_load(candidate)
        if loaded is not None:
            if require_object and not isinstance(loaded, dict):
                continue
            return loaded
    return None


def _extract_balanced_json(text: str, *, require_object: bool = False) -> object | None:
    """从文本中用括号平衡扫描提取 JSON。

    找到每个 ``{``（或 ``require_object=False`` 时的 ``{`` ``[``），
    向前扫描直到找到匹配的闭合括号，对该区间的子串尝试 ``json.loads``。

    Args:
        text: LLM 返回的原始文本。
        require_object: 若为 ``True`` 则只扫描 ``{`` 开头的区间。

    Returns:
        解析成功返回 Python 对象，否则返回 ``None``。
    """
    opening_chars = "{" if require_object else "{["
    start_indexes = [index for index, char in enumerate(text) if char in opening_chars]
    for start_index in start_indexes:
        end_index = _find_balanced_end(text, start_index)
        if end_index is None:
            continue
        candidate = text[start_index : end_index + 1]
        loaded = _try_json_load(candidate)
        if loaded is not None:
            if require_object and not isinstance(loaded, dict):
                continue
            return loaded
    return None


def _find_balanced_end(text: str, start_index: int) -> int | None:
    """从起始位置向前扫描，找到第一个匹配的闭合括号。

    正确处理字符串内转义与嵌套括号；只匹配与起始括号类型一致的闭合。

    Args:
        text: 待扫描的文本。
        start_index: 起始括号在文本中的索引（字符位置）。

    Returns:
        匹配的闭合括号索引；若未找到平衡的闭合则返回 ``None``。
    """
    opening = text[start_index]
    expected_closing = "}" if opening == "{" else "]"
    stack: list[str] = [opening]
    in_string = False
    escaped = False

    for index in range(start_index + 1, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char in "{[":
            stack.append(char)
            continue
        if char not in "}]":
            continue
        if not stack:
            return None
        current_open = stack.pop()
        if (current_open == "{" and char != "}") or (current_open == "[" and char != "]"):
            return None
        if not stack:
            if char != expected_closing:
                return None
            return index
    return None
