from __future__ import annotations

import asyncio

import httpx


RETRIABLE_STATUS_CODES = {429, 502, 503, 504}


class OpenAIResponsesGateway:
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise RuntimeError("缺少 API Key，无法生成总结。")

        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def create_text(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "input": prompt,
            "text": {"format": {"type": "text"}},
        }
        try:
            raw_response = await self._post_with_retry(payload)
        except httpx.HTTPStatusError as error:
            body = error.response.text
            raise RuntimeError(f"OpenAI 请求失败: {error.response.status_code} {body}") from error
        except httpx.HTTPError as error:
            raise RuntimeError(f"OpenAI 请求失败: {error}") from error

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

    async def _post_with_retry(self, payload: dict[str, object]) -> dict[str, object]:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=30.0),
                ) as client:
                    response = await client.post(
                        self._base_url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    if response.status_code in RETRIABLE_STATUS_CODES:
                        raise _RetriableStatusError(response)
                    response.raise_for_status()
                    return response.json()
            except (httpx.TransportError, _RetriableStatusError):
                if attempt == 2:
                    raise
                await asyncio.sleep(min(2 ** attempt, 8))
        raise RuntimeError("OpenAI 请求失败: retried without response")


class _RetriableStatusError(httpx.HTTPStatusError):
    def __init__(self, response: httpx.Response) -> None:
        super().__init__(
            f"Retriable OpenAI status: {response.status_code}",
            request=response.request,
            response=response,
        )
