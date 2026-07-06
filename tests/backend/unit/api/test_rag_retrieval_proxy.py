from __future__ import annotations

import unittest
from types import SimpleNamespace

from tests import _path_setup  # noqa: F401

from backend.api.adapters.rag_retrieval_proxy import _RagModelAwareRetrievalService


class RagRetrievalProxyTests(unittest.TestCase):
    def test_invalidate_discards_cached_service_instance(self) -> None:
        created_services: list[FakeSeriesRetrievalService] = []

        def factory() -> FakeSeriesRetrievalService:
            service = FakeSeriesRetrievalService()
            created_services.append(service)
            return service

        proxy = _RagModelAwareRetrievalService(
            rag_model_manager=FakeRagModelManager(),
            factory=factory,
            settings_loader=lambda: SimpleNamespace(
                agent_retrieval=SimpleNamespace(embedding_device="cpu", max_hits=5)
            ),
        )

        proxy.search(query="first")
        proxy.invalidate()
        proxy.search(query="second")

        self.assertEqual(len(created_services), 2)
        self.assertEqual(created_services[0].invalidate_calls, 1)


class FakeSeriesRetrievalService:
    def __init__(self) -> None:
        self.invalidate_calls = 0

    def search(self, **kwargs):
        return kwargs

    def invalidate(self) -> None:
        self.invalidate_calls += 1


class FakeRagModelManager:
    def is_downloaded(self, key: str) -> bool:
        return key in {"embedding", "reranker"}


if __name__ == "__main__":
    unittest.main()
