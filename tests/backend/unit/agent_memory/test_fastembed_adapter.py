from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.video_summary.infrastructure.agent_memory.fastembed_adapter import FastEmbedEmbedding


class FastEmbedEmbeddingTests(unittest.TestCase):
    def test_uses_fastembed_for_text_and_query_embeddings(self) -> None:
        with patch(
            "backend.video_summary.infrastructure.agent_memory.fastembed_adapter._load_text_embedding_cls",
            return_value=_FakeTextEmbedding,
        ):
            embedding = FastEmbedEmbedding(
                model_name="BAAI/bge-small-zh-v1.5",
                device="cpu",
                embed_batch_size=2,
                cache_dir="data/models/fastembed",
            )

            self.assertEqual(_FakeTextEmbedding.created[-1]["cache_dir"], "data/models/fastembed")
            self.assertEqual(embedding._get_query_embedding("问题"), [2.0, 3.0])
            self.assertEqual(embedding._get_text_embeddings(["a", "abcd"]), [[1.0, 2.0], [4.0, 5.0]])

    def test_gpu_device_uses_cuda_provider_without_cpu_fallback(self) -> None:
        _FakeTextEmbedding.created = []
        with patch(
            "backend.video_summary.infrastructure.agent_memory.fastembed_adapter._load_text_embedding_cls",
            return_value=_FakeTextEmbedding,
        ):
            FastEmbedEmbedding(model_name="model", device="gpu", embed_batch_size=4)

        self.assertEqual(_FakeTextEmbedding.created[-1]["providers"], ["CUDAExecutionProvider"])
        self.assertTrue(_FakeTextEmbedding.created[-1]["cuda"])


class _FakeTextEmbedding:
    created = []

    def __init__(self, *, model_name: str, cache_dir=None, providers=None, cuda=False, **kwargs) -> None:
        self.created.append(
            {
                "model_name": model_name,
                "cache_dir": cache_dir,
                "providers": providers,
                "cuda": cuda,
                "kwargs": kwargs,
            }
        )

    def embed(self, texts, batch_size=256):
        del batch_size
        for text in texts:
            yield [float(len(text)), float(len(text) + 1)]

    def query_embed(self, query):
        return iter([[float(len(query)), float(len(query) + 1)]])


if __name__ == "__main__":
    unittest.main()
