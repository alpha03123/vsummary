"""Agent 内部使用的 JSON 协议工具。

为 LLM 结构化输出（json_schema / json_object 模式）提供轻量级的解析
入口；设计上只做「剥空白 + 委托 Pydantic 校验」这一最小动作，便于在不
依赖 LangChain 解析器的情况下复用。
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel


ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


def parse_json_completion(raw_output: str, response_model: type[ResponseModelT]) -> ResponseModelT:
    """把 LLM 的原始字符串响应解析为目标 Pydantic 模型。

    约定：模型返回的字符串必须是合法 JSON 文本（与 LiteLLM 的
    `response_format=json_schema` / `json_object` 配合），本函数只做
    首尾空白裁剪后直接交给 Pydantic 进行结构化校验，不会做 JSON
    片段提取或 Markdown 代码块剥离——若上游模型未启用严格 JSON 模式，
    调用方应自行预处理。

    Args:
        raw_output: LLM 返回的原始字符串。
        response_model: 用于校验与反序列化的目标 Pydantic 模型类。

    Returns:
        已通过校验的 `response_model` 实例。

    Raises:
        ValueError: 当 `raw_output` 去除首尾空白后为空字符串时抛出，
            提示模型未产生任何可解析内容。
        pydantic.ValidationError: 当 JSON 文本存在但与 `response_model`
            的 schema 不匹配时由 Pydantic 抛出。
    """
    payload = raw_output.strip()
    if not payload:
        raise ValueError("模型返回为空，无法解析 JSON。")
    return response_model.model_validate_json(payload)
