from __future__ import annotations

import re
from urllib.parse import urlparse


def normalize_provider_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if not normalized:
        return normalized
    for endpoint in ("/chat/completions", "/responses", "/completions"):
        if normalized.endswith(endpoint):
            return normalized[: -len(endpoint)].rstrip("/")
    return normalized


def resolve_openai_compatible_api_base_url(value: str) -> str:
    normalized = normalize_provider_base_url(value)
    parsed = urlparse(normalized)
    if not parsed.scheme or not parsed.netloc:
        return normalized

    path = parsed.path.rstrip("/")
    if not re.search(r"/v\d+$", path):
        path = f"{path}/v1" if path else "/v1"

    return f"{parsed.scheme}://{parsed.netloc}{path}"
