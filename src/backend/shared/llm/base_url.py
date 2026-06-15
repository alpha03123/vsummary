"""LLM 服务的 base URL 归一化工具。

把用户配置的各种 OpenAI 兼容服务地址统一为 ``{origin}/v1`` 格式，
供 LiteLLM gateway 使用。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


def normalize_provider_base_url(value: str) -> str:
    """归一化提供商 base URL：去除尾部斜杠与已知 API 端点后缀。

    会自动剥离 ``/chat/completions``、``/responses``、``/completions``
    等常见后缀，方便统一拼接路径。

    Args:
        value: 用户配置的原始 URL 字符串。

    Returns:
        归一化后的 URL；若输入为空则返回空字符串。
    """
    normalized = value.strip().rstrip("/")
    if not normalized:
        return normalized
    for endpoint in ("/chat/completions", "/responses", "/completions"):
        if normalized.endswith(endpoint):
            return normalized[: -len(endpoint)].rstrip("/")
    return normalized


def resolve_openai_compatible_api_base_url(value: str) -> str:
    """将任意 OpenAI 兼容地址解析为标准 ``{origin}/v1`` 格式。

    先调用 ``normalize_provider_base_url`` 剥离尾部端点，再确保路径以
    ``/v1`` 结尾；已包含版本号（如 ``/v2``）则不再追加。

    Args:
        value: 用户配置的原始 URL 字符串。

    Returns:
        形如 ``https://api.openai.com/v1`` 的归一化地址；若输入不含
        scheme 或 netloc 则直接返回归一化后的值（不做 /v1 追加）。
    """
    normalized = normalize_provider_base_url(value)
    parsed = urlparse(normalized)
    if not parsed.scheme or not parsed.netloc:
        return normalized

    path = parsed.path.rstrip("/")
    if not re.search(r"/v\d+$", path):
        path = f"{path}/v1" if path else "/v1"

    return f"{parsed.scheme}://{parsed.netloc}{path}"
