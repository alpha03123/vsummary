from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel


ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


def parse_json_completion(raw_output: str, response_model: type[ResponseModelT]) -> ResponseModelT:
    payload = strip_optional_code_fence(raw_output)
    return response_model.model_validate_json(payload)


def strip_optional_code_fence(text: str) -> str:
    normalized = text.strip()
    if not normalized.startswith("```"):
        return normalized
    lines = normalized.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return normalized
