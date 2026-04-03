from __future__ import annotations

import json
import urllib.error
import urllib.request


class OpenAIResponsesGateway:
    def __init__(self, model: str, base_url: str, api_key: str) -> None:
        if not api_key:
            raise RuntimeError("缺少 API Key，无法生成总结。")

        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    def create_text(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "input": prompt,
            "text": {"format": {"type": "text"}},
        }
        request = urllib.request.Request(
            self._base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI 请求失败: {error.code} {body}") from error

        output_text = raw_response.get("output_text")
        if output_text:
            return output_text.strip()

        output_items = raw_response.get("output", [])
        content_parts: list[str] = []
        for item in output_items:
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    content_parts.append(content["text"].strip())
        if content_parts:
            return "\n".join(part for part in content_parts if part)

        raise RuntimeError(f"OpenAI 返回中缺少 output_text: {raw_response}")
