from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel


ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


def parse_json_completion(raw_output: str, response_model: type[ResponseModelT]) -> ResponseModelT:
    payload = raw_output.strip()
    if not payload:
        raise ValueError("模型返回为空，无法解析 JSON。")
    return response_model.model_validate_json(payload)
