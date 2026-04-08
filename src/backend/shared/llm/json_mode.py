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
    payload = extract_json_document(raw_text)
    return response_model.model_validate(payload)


def describe_validation_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return json.dumps(error.errors(include_url=False), ensure_ascii=False)
    return str(error)


def extract_json_document(raw_text: str) -> object:
    text = raw_text.strip()
    if not text:
        raise ValueError("模型返回为空，无法解析 JSON。")

    direct_value = _try_json_load(text)
    if direct_value is not None:
        return direct_value

    fenced_value = _extract_fenced_json(text)
    if fenced_value is not None:
        return fenced_value

    balanced_value = _extract_balanced_json(text)
    if balanced_value is not None:
        return balanced_value

    raise ValueError("模型返回中未找到可解析的 JSON。")


def _try_json_load(candidate: str) -> object | None:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _extract_fenced_json(text: str) -> object | None:
    matches = re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    for match in matches:
        candidate = match.group(1).strip()
        loaded = _try_json_load(candidate)
        if loaded is not None:
            return loaded
    return None


def _extract_balanced_json(text: str) -> object | None:
    start_indexes = [index for index, char in enumerate(text) if char in "{["]
    for start_index in start_indexes:
        end_index = _find_balanced_end(text, start_index)
        if end_index is None:
            continue
        candidate = text[start_index : end_index + 1]
        loaded = _try_json_load(candidate)
        if loaded is not None:
            return loaded
    return None


def _find_balanced_end(text: str, start_index: int) -> int | None:
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
