from __future__ import annotations

import httpx
import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel
from typing import TypeVar


StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


class OpenAICompletionGateway:
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise RuntimeError("缺少 API Key，无法生成总结。")

        self._model = model
        self._http_client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=30.0),
        )
        self._openai_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            http_client=self._http_client,
            max_retries=2,
        )
        self._structured_client = instructor.from_openai(self._openai_client)

    async def create_text(self, prompt: str) -> str:
        try:
            response = await self._openai_client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
        except httpx.HTTPError as error:
            raise RuntimeError(f"OpenAI 请求失败: {error}") from error

        content = response.choices[0].message.content
        if isinstance(content, str) and content.strip():
            return content.strip()
        raise RuntimeError("模型返回缺少 message.content。")

    async def create_structured_completion(
        self,
        *,
        prompt: str,
        response_model: type[StructuredResponse],
    ) -> StructuredResponse:
        try:
            return await self._structured_client.chat.completions.create(
                model=self._model,
                response_model=response_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_retries=3,
            )
        except (httpx.HTTPError, Exception) as error:
            if isinstance(error, RuntimeError):
                raise
            raise RuntimeError(f"OpenAI 结构化请求失败: {error}") from error
