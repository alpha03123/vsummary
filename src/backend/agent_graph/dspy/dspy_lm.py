from __future__ import annotations

import json
from types import SimpleNamespace

import requests
from dspy.clients.base_lm import BaseLM


class ProxyStreamingLM(BaseLM):
    def __init__(self, *, model: str, api_base: str, api_key: str, request_sender=None, **kwargs) -> None:
        super().__init__(model=model, model_type="chat", **kwargs)
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._request_sender = request_sender or requests.post

    def forward(self, prompt=None, messages=None, **kwargs):
        del prompt
        payload = {
            "model": self.model.split("/", 1)[-1] if "/" in self.model else self.model,
            "messages": messages or [],
            "temperature": kwargs.get("temperature", self.kwargs.get("temperature", 0.0)),
            "stream": True,
        }
        response = self._request_sender(
            url=f"{self._api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=kwargs.get("timeout", 120),
            stream=True,
        )
        response.raise_for_status()

        content_parts: list[str] = []
        usage: dict[str, int] = {}
        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace")
            if not line.startswith("data: "):
                continue
            payload_text = line[6:]
            if payload_text == "[DONE]":
                continue
            chunk = json.loads(payload_text)
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                piece = delta.get("content")
                if isinstance(piece, str) and piece:
                    content_parts.append(piece)
            if isinstance(chunk.get("usage"), dict):
                usage = dict(chunk["usage"])

        full_text = "".join(content_parts)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=full_text),
                    finish_reason="stop",
                )
            ],
            usage=usage,
            model=self.model,
        )
