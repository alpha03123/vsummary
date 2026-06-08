from __future__ import annotations

from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from pydantic import PrivateAttr


class FastEmbedEmbedding(BaseEmbedding):
    device: str = "cpu"
    _embedding: Any = PrivateAttr()

    def __init__(
        self,
        *,
        model_name: str,
        device: str = "cpu",
        embed_batch_size: int = 8,
        cache_dir: str | None = None,
    ) -> None:
        super().__init__(model_name=model_name, embed_batch_size=embed_batch_size)
        self.device = _normalize_device(device)
        self._embedding = _create_text_embedding(
            model_name=model_name,
            device=self.device,
            cache_dir=cache_dir,
        )

    def _get_query_embedding(self, query: str) -> list[float]:
        return [float(value) for value in next(self._embedding.query_embed(query))]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embeddings([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [
            [float(value) for value in embedding]
            for embedding in self._embedding.embed(texts, batch_size=self.embed_batch_size)
        ]


def build_fastembed_embedding(
    *,
    model_name: str,
    device: str,
    embed_batch_size: int,
    cache_dir: str | None = None,
) -> FastEmbedEmbedding:
    return FastEmbedEmbedding(
        model_name=model_name,
        device=device,
        embed_batch_size=embed_batch_size,
        cache_dir=cache_dir,
    )


def _create_text_embedding(*, model_name: str, device: str, cache_dir: str | None):
    text_embedding_cls = _load_text_embedding_cls()
    kwargs: dict[str, object] = {"model_name": model_name}
    if cache_dir is not None:
        kwargs["cache_dir"] = cache_dir
    if device == "gpu":
        kwargs["providers"] = ["CUDAExecutionProvider"]
        kwargs["cuda"] = True
    elif device == "cpu":
        kwargs["providers"] = ["CPUExecutionProvider"]
    return text_embedding_cls(**kwargs)


def _load_text_embedding_cls():
    try:
        from fastembed import TextEmbedding
    except ImportError as error:
        raise RuntimeError("缺少本地 embedding 依赖。请安装 fastembed 或 fastembed-gpu。") from error
    return TextEmbedding


def _normalize_device(device: str) -> str:
    normalized = (device or "cpu").strip().lower()
    if normalized == "cuda":
        return "gpu"
    if normalized == "auto":
        return "cpu"
    if normalized in {"cpu", "gpu"}:
        return normalized
    raise ValueError(f"Unsupported fastembed device: {device!r}")
