from __future__ import annotations

from threading import Lock
from typing import Callable

from backend.video_summary.infrastructure.rag.agent_memory import SeriesRetrievalService
from backend.video_summary.infrastructure.rag.rag_models import RAG_EMBEDDING_REQUIRED_MESSAGE, RagModelManager


class _RagModelAwareRetrievalService:
    def __init__(
        self,
        *,
        rag_model_manager: RagModelManager,
        factory: Callable[[], SeriesRetrievalService],
        settings_loader: Callable[[], object],
    ) -> None:
        self._rag_model_manager = rag_model_manager
        self._factory = factory
        self._settings_loader = settings_loader
        self._service: SeriesRetrievalService | None = None
        self._signature: tuple[bool, bool, str] | None = None
        self._lock = Lock()

    def search(self, **kwargs):
        return self._require_service().search(**kwargs)

    def default_max_hits(self) -> int:
        return self._settings_loader().agent_retrieval.max_hits

    def refresh(self) -> None:
        self._require_service().refresh()

    def refresh_all(self) -> None:
        self._require_service().refresh_all()

    def upsert_video(self, series_id: str, video_id: str) -> None:
        self._require_service().upsert_video(series_id, video_id)

    def delete_video(self, series_id: str, video_id: str) -> None:
        self._require_service().delete_video(series_id, video_id)

    def delete_series(self, series_id: str) -> None:
        self._require_service().delete_series(series_id)

    def invalidate(self) -> None:
        with self._lock:
            if self._service is not None:
                self._service.invalidate()

    def _require_service(self) -> SeriesRetrievalService:
        with self._lock:
            if not self._rag_model_manager.is_downloaded("embedding"):
                raise RuntimeError(RAG_EMBEDDING_REQUIRED_MESSAGE)
            signature = self._build_signature()
            if self._service is None or self._signature != signature:
                self._service = self._factory()
                self._signature = signature
            return self._service

    def _build_signature(self) -> tuple[bool, bool, str]:
        settings = self._settings_loader()
        return (
            self._rag_model_manager.is_downloaded("embedding"),
            self._rag_model_manager.is_downloaded("reranker"),
            settings.agent_retrieval.embedding_device,
        )