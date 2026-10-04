"""HTTP embedding and reranking adapters using existing LlamaIndex ports."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx
from llama_index.core.embeddings import BaseEmbedding
from pydantic import PrivateAttr

from backend.core.concurrency import request_slot
from backend.video_summary.infrastructure.rag.agent_memory.pinpoint import (
    SemanticScorer,
)


class ModelApiError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool, retry_after: float | None = None):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class ModelApiSettings:
    endpoint: str
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: float = 60
    dimensions: int | None = None

    def __post_init__(self):
        uri = urlsplit(self.endpoint)
        if (
            uri.scheme not in {"http", "https"}
            or not uri.netloc
            or uri.query
            or uri.fragment
        ):
            raise ValueError(
                "Model API endpoint must be an absolute HTTP URL without query or fragment."
            )
        if (
            not self.model.strip()
            or not self.api_key.strip()
            or self.timeout_seconds <= 0
        ):
            raise ValueError("Model API requires model, key and positive timeout.")
        if self.dimensions is not None and self.dimensions < 1:
            raise ValueError("Embedding dimensions must be positive.")


def _request(
    settings: ModelApiSettings, resource: str, payload: dict, client: httpx.Client
) -> dict:
    with request_slot(resource):
        try:
            response = client.post(
                settings.endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {settings.api_key}"},
                timeout=settings.timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise ModelApiError("provider_unavailable", retryable=True) from error
    if response.status_code == 429 or response.status_code >= 500:
        value = response.headers.get("Retry-After")
        delay = float(value) if value and value.isdecimal() else None
        raise ModelApiError(
            "provider_rate_limited"
            if response.status_code == 429
            else "provider_unavailable",
            retryable=True,
            retry_after=delay,
        )
    if not response.is_success:
        raise ModelApiError("provider_request_rejected", retryable=False)
    try:
        result = response.json()
    except ValueError as error:
        raise ModelApiError("provider_invalid_response", retryable=False) from error
    if not isinstance(result, dict):
        raise ModelApiError("provider_invalid_response", retryable=False)
    return result


class ApiEmbedding(BaseEmbedding):
    """OpenAI-compatible /embeddings, indexed responses restored to input order."""

    _settings: ModelApiSettings = PrivateAttr()
    _client: httpx.Client = PrivateAttr()
    _dimensions: int | None = PrivateAttr()

    def __init__(
        self,
        settings: ModelApiSettings,
        *,
        batch_size: int,
        client: httpx.Client | None = None,
    ):
        super().__init__(model_name=settings.model, embed_batch_size=batch_size)
        self._settings = settings
        self._client = client or httpx.Client()
        self._dimensions = settings.dimensions

    def close(self):
        self._client.close()

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._get_text_embedding(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await asyncio.to_thread(self._get_query_embedding, query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embeddings([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, Any] = {"model": self.model_name, "input": texts}
        if self._settings.dimensions is not None:
            payload["dimensions"] = self._settings.dimensions
        data = _request(self._settings, "embedding", payload, self._client).get("data")
        try:
            if not isinstance(data, list) or len(data) != len(texts):
                raise ValueError("embedding count")
            ordered: dict[int, list[float]] = {}
            for item in data:
                index = item["index"]
                vector = item["embedding"]
                if (
                    type(index) is not int
                    or index in ordered
                    or index not in range(len(texts))
                ):
                    raise ValueError("embedding index")
                if not isinstance(vector, list) or not vector:
                    raise ValueError("embedding vector")
                if any(
                    type(value) not in (int, float) or not math.isfinite(value)
                    for value in vector
                ):
                    raise ValueError("embedding values")
                dimension = self._dimensions or len(vector)
                if len(vector) != dimension:
                    raise ValueError("embedding dimension")
                self._dimensions = dimension
                ordered[index] = [float(value) for value in vector]
            return [ordered[index] for index in range(len(texts))]
        except (KeyError, TypeError, ValueError) as error:
            raise ModelApiError(
                "provider_invalid_embedding", retryable=False
            ) from error


class ApiReranker(SemanticScorer):
    """Indexed /rerank protocol; every document must have a finite score."""

    def __init__(
        self, settings: ModelApiSettings, *, client: httpx.Client | None = None
    ):
        self.settings = settings
        self.client = client or httpx.Client()

    def close(self):
        self.client.close()

    def score(self, *, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        result = _request(
            self.settings,
            "rerank",
            {
                "model": self.settings.model,
                "query": query,
                "documents": texts,
                "top_n": len(texts),
            },
            self.client,
        ).get("results")
        try:
            if not isinstance(result, list) or len(result) != len(texts):
                raise ValueError("rerank count")
            scores = {}
            for item in result:
                index, score = item["index"], item["relevance_score"]
                if (
                    type(index) is not int
                    or index in scores
                    or index not in range(len(texts))
                ):
                    raise ValueError("rerank index")
                if type(score) not in (int, float) or not math.isfinite(score):
                    raise ValueError("rerank score")
                scores[index] = float(score)
            return [scores[index] for index in range(len(texts))]
        except (KeyError, TypeError, ValueError) as error:
            raise ModelApiError("provider_invalid_rerank", retryable=False) from error
