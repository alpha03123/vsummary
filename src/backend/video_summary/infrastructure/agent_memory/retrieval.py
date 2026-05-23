from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import logging
from pathlib import Path
from threading import RLock, Thread

import lancedb
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.vector_stores import FilterCondition, FilterOperator, MetadataFilter, MetadataFilters
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from backend.shared.filesystem import atomic_write_text
from backend.video_summary.infrastructure.settings import (
    AgentRetrievalSettings,
    DEFAULT_AGENT_RETRIEVAL_MAX_HITS,
    DEFAULT_AGENT_RETRIEVAL_RERANK_ENABLED,
    apply_runtime_env_overrides,
    load_settings,
)
from backend.video_summary.library.ports import VideoLibraryReader

INDEX_SCHEMA_VERSION = 4
INDEX_TABLE_NAME = f"agent_graph_evidence_v{INDEX_SCHEMA_VERSION}"
RERANK_EMBEDDING_MULTIPLIER = 4
LANCEDB_OPTIMIZE_CLEANUP_OLDER_THAN = timedelta(minutes=10)
LOGGER = logging.getLogger(__name__)
SeriesSignature = tuple[str, ...]
SeriesSignatureMap = dict[str, SeriesSignature]
COMMON_METADATA_DEFAULTS: dict[str, object] = {
    "doc_id": "",
    "series_id": "",
    "video_id": "",
    "title": "",
    "source_type": "",
    "source_family": "",
    "chapter_title": "",
    "start_seconds": None,
    "end_seconds": None,
    "note_id": "",
    "note_source": "",
    "card_id": "",
    "card_kind": "",
}


@dataclass(frozen=True)
class RetrievalDocument:
    text: str
    metadata: dict[str, object]


class SeriesRetrievalService:
    def __init__(
        self,
        *,
        workspace: VideoLibraryReader,
        db_uri: str,
        embed_model=None,
        reranker=None,
        rerank_enabled: bool | None = None,
        root_dir: Path | None = None,
    ) -> None:
        self._workspace = workspace
        self._db_uri = db_uri
        self._root_dir = root_dir
        self._embed_model = embed_model or _build_default_embed_model(root_dir)
        self._reranker = reranker
        self._rerank_enabled_override = rerank_enabled
        self._index: VectorStoreIndex | None = None
        self._series_signatures: SeriesSignatureMap | None = None
        self._index_lock = RLock()

    def invalidate(self) -> None:
        with self._index_lock:
            self._index = None
            self._series_signatures = None

    def refresh(self) -> None:
        self.refresh_all()

    def refresh_all(self) -> None:
        with self._index_lock:
            self._index = None
            self._series_signatures = None
            self._rebuild_index()

    def refresh_series(self, series_id: str) -> None:
        with self._index_lock:
            if not _table_exists(self._db_uri, INDEX_TABLE_NAME):
                documents = _build_documents_for_series(self._workspace, series_id=series_id)
                if documents:
                    self._write_documents(documents, mode="overwrite")
                self._write_series_signature(series_id)
                self.invalidate()
                return
            self._delete_series_rows(series_id=series_id)
            documents = _build_documents_for_series(self._workspace, series_id=series_id)
            if documents:
                self._append_documents(documents)
            self._write_series_signature(series_id)
            self.invalidate()

    def upsert_video(self, series_id: str, video_id: str) -> None:
        with self._index_lock:
            if not self._is_incremental_mutation_ready():
                self.refresh_series(series_id)
                return
            self._delete_video_rows(series_id=series_id, video_id=video_id)
            documents = _build_documents_for_video(self._workspace, series_id=series_id, video_id=video_id)
            if documents:
                self._append_documents(documents)
            self._finalize_incremental_mutation(series_id)

    def delete_video(self, series_id: str, video_id: str) -> None:
        with self._index_lock:
            if not self._is_incremental_mutation_ready():
                self.refresh_series(series_id)
                return
            self._delete_video_rows(series_id=series_id, video_id=video_id)
            self._finalize_incremental_mutation(series_id)

    def delete_series(self, series_id: str) -> None:
        with self._index_lock:
            if not self._is_incremental_mutation_ready():
                self._remove_series_signature(series_id)
                return
            self._delete_series_rows(series_id=series_id)
            self._finalize_incremental_mutation(series_id)
            try:
                _optimize_lancedb_table(self._db_uri, INDEX_TABLE_NAME)
            except Exception:
                LOGGER.exception("lancedb table optimize failed after deleting series %s", series_id)

    def search(
        self,
        *,
        scope_type: str,
        series_id: str,
        video_id: str,
        query: str,
        target_source: str,
        source_tags: list[str] | None = None,
        expand_context: bool,
        context_window_seconds: int,
        max_hits: int | None,
    ) -> dict[str, object]:
        with self._index_lock:
            index = self._require_index(series_id)
            final_max_hits = self._resolve_final_max_hits(max_hits)
            rerank_enabled = self._resolve_rerank_enabled()
            embedding_top_k = (
                final_max_hits * RERANK_EMBEDDING_MULTIPLIER
                if rerank_enabled and self._reranker is not None
                else final_max_hits
            )
            retriever = index.as_retriever(
                similarity_top_k=embedding_top_k,
                filters=_build_filters(
                    scope_type=scope_type,
                    series_id=series_id,
                    video_id=video_id,
                    target_source=target_source,
                    source_tags=source_tags or [],
                ),
            )
            nodes = retriever.retrieve(query)
        hits: list[dict[str, object]] = []
        for item in nodes:
            metadata = dict(getattr(item.node, "metadata", {}) or {})
            hit = {
                "doc_id": str(metadata.get("doc_id", "")),
                "series_id": str(metadata.get("series_id", "")),
                "video_id": str(metadata.get("video_id", "")),
                "title": str(metadata.get("title", "")),
                "source_type": str(metadata.get("source_type", "")),
                "source_family": str(metadata.get("source_family", "")),
                "score": float(item.score or 0.0),
                "start_seconds": metadata.get("start_seconds"),
                "end_seconds": metadata.get("end_seconds"),
                "chapter_title": metadata.get("chapter_title"),
                "text": item.node.get_content(),
                "snippet": item.node.get_content(),
            }
            if hit["source_type"] == "transcript_chunk" and expand_context:
                hit = _expand_transcript_hit(
                    workspace=self._workspace,
                    series_id=series_id,
                    video_id=hit["video_id"],
                    hit=hit,
                    context_window_seconds=context_window_seconds,
                )
            hits.append(hit)

        if rerank_enabled and self._reranker is not None and hits:
            rerank_scores = self._reranker.score(
                query=query,
                texts=[str(hit.get("text", "")) for hit in hits],
            )
            scored_hits = [
                (
                    float(rerank_scores[index]) if index < len(rerank_scores) else 0.0,
                    hit,
                )
                for index, hit in enumerate(hits)
            ]
            scored_hits.sort(key=lambda item: (-item[0], str(item[1]["video_id"]), str(item[1]["source_type"])))
            hits = [hit for _, hit in scored_hits]
        else:
            hits.sort(key=lambda item: (-float(item["score"]), str(item["video_id"]), str(item["source_type"])))
        hits = hits[:final_max_hits]
        for index, hit in enumerate(hits, start=1):
            hit["evidence_id"] = f"e{index}"

        return {
            "scope_type": scope_type,
            "series_id": series_id,
            "video_id": video_id,
            "query": query,
            "target_source": target_source,
            "source_tags": list(source_tags or []),
            "hits": hits,
        }

    def default_max_hits(self) -> int:
        return self._load_runtime_retrieval_settings().max_hits

    def _get_or_build_index(self) -> VectorStoreIndex:
        signatures = _build_series_signatures(self._workspace)
        if self._index is not None and self._series_signatures == signatures:
            return self._index
        loaded = self._try_load_existing_index()
        if loaded is not None:
            self._index = loaded
            self._series_signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
            return loaded
        return self._rebuild_index()

    def _require_index(self, series_id: str) -> VectorStoreIndex:
        if self._index is not None:
            if self._is_series_signature_stale(series_id):
                self._refresh_series_async(series_id)
            return self._index
        loaded = self._try_load_existing_index()
        if loaded is not None:
            self._index = loaded
            self._series_signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
            if self._is_series_signature_stale(series_id):
                self._refresh_series_async(series_id)
            return loaded
        self.refresh_series(series_id)
        if self._index is not None:
            return self._index
        loaded = self._try_load_existing_index()
        if loaded is None:
            raise RuntimeError("Agent retrieval index 尚未就绪，请先执行知识记忆刷新。")
        self._index = loaded
        self._series_signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
        return loaded

    def _rebuild_index(self) -> VectorStoreIndex:
        signatures = _build_series_signatures(self._workspace)
        documents = _to_llama_documents(_build_documents(self._workspace))
        vector_store = LanceDBVectorStore(
            uri=self._db_uri,
            table_name=INDEX_TABLE_NAME,
            mode="overwrite",
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        self._index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            embed_model=self._embed_model,
            show_progress=False,
        )
        self._series_signatures = signatures
        _write_signature_file(self._db_uri, INDEX_TABLE_NAME, signatures)
        return self._index

    def _append_documents(self, documents: list[RetrievalDocument]) -> None:
        self._write_documents(documents, mode="append")

    def _write_documents(self, documents: list[RetrievalDocument], *, mode: str) -> None:
        vector_store = LanceDBVectorStore(
            uri=self._db_uri,
            table_name=INDEX_TABLE_NAME,
            mode=mode,
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex.from_documents(
            _to_llama_documents(documents),
            storage_context=storage_context,
            embed_model=self._embed_model,
            show_progress=False,
        )

    def _is_incremental_mutation_ready(self) -> bool:
        return (
            _table_exists(self._db_uri, INDEX_TABLE_NAME)
            and _read_signature_file(self._db_uri, INDEX_TABLE_NAME) is not None
        )

    def _finalize_incremental_mutation(self, series_id: str) -> None:
        self.invalidate()
        signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
        current_signature = _build_series_signature(self._workspace, series_id)
        if current_signature:
            signatures[series_id] = current_signature
        else:
            signatures.pop(series_id, None)
        _write_signature_file(self._db_uri, INDEX_TABLE_NAME, signatures)

    def _write_series_signature(self, series_id: str) -> None:
        signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
        current_signature = _build_series_signature(self._workspace, series_id)
        if current_signature:
            signatures[series_id] = current_signature
        else:
            signatures.pop(series_id, None)
        _write_signature_file(self._db_uri, INDEX_TABLE_NAME, signatures)

    def _remove_series_signature(self, series_id: str) -> None:
        signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
        signatures.pop(series_id, None)
        _write_signature_file(self._db_uri, INDEX_TABLE_NAME, signatures)

    def _is_series_signature_stale(self, series_id: str) -> bool:
        if not series_id:
            return False
        stored_signatures = self._series_signatures
        if stored_signatures is None:
            stored_signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
            self._series_signatures = stored_signatures
        return stored_signatures.get(series_id) != _build_series_signature(self._workspace, series_id)

    def _refresh_series_async(self, series_id: str) -> None:
        if not series_id:
            return

        def refresh() -> None:
            try:
                self.refresh_series(series_id)
            except Exception:
                LOGGER.exception("series index refresh failed for %s", series_id)

        Thread(target=refresh, daemon=True).start()

    def _delete_video_rows(self, *, series_id: str, video_id: str) -> None:
        _delete_rows(
            db_uri=self._db_uri,
            table_name=INDEX_TABLE_NAME,
            where=(
                f"metadata.series_id = '{_escape_lance_string(series_id)}' "
                f"and metadata.video_id = '{_escape_lance_string(video_id)}'"
            ),
        )

    def _delete_series_rows(self, *, series_id: str) -> None:
        _delete_rows(
            db_uri=self._db_uri,
            table_name=INDEX_TABLE_NAME,
            where=f"metadata.series_id = '{_escape_lance_string(series_id)}'",
        )

    def _try_load_existing_index(self) -> VectorStoreIndex | None:
        if not _table_exists(self._db_uri, INDEX_TABLE_NAME):
            return None
        vector_store = LanceDBVectorStore(
            uri=self._db_uri,
            table_name=INDEX_TABLE_NAME,
        )
        return VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=self._embed_model,
        )

    def _resolve_final_max_hits(self, max_hits: int | None) -> int:
        if max_hits is not None:
            if max_hits <= 0:
                raise ValueError("max_hits 必须是正整数。")
            return max_hits
        return self.default_max_hits()

    def _resolve_rerank_enabled(self) -> bool:
        if self._rerank_enabled_override is not None:
            return self._rerank_enabled_override
        return self._load_runtime_retrieval_settings().rerank_enabled

    def _load_runtime_retrieval_settings(self) -> AgentRetrievalSettings:
        if self._root_dir is None:
            return AgentRetrievalSettings(
                embedding_provider="local_huggingface",
                embedding_model="BAAI/bge-base-zh-v1.5",
                embedding_device="cpu",
                embedding_batch_size=8,
                max_hits=DEFAULT_AGENT_RETRIEVAL_MAX_HITS,
                rerank_enabled=DEFAULT_AGENT_RETRIEVAL_RERANK_ENABLED,
            )
        return load_settings(self._root_dir / "config" / "settings.toml", self._root_dir).agent_retrieval


class MetaStateReader:
    def __init__(self, *, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def read(self, *, scope_type: str, series_id: str, video_id: str) -> dict[str, object]:
        if scope_type == "video":
            tools = self._workspace.get_video_workspace_tools(series_id, video_id)
            if tools is None:
                return {
                    "scope_type": scope_type,
                    "series_id": series_id,
                    "video_id": video_id,
                    "error": "video_tools_not_found",
                }
            return {
                "scope_type": scope_type,
                "series_id": series_id,
                "video_id": video_id,
                "overview": _serialize_tool_state(tools.overview),
                "knowledge_cards": _serialize_tool_state(tools.knowledge_cards),
                "mindmap": _serialize_tool_state(tools.mindmap),
                "notes": _serialize_tool_state(tools.notes),
                "preview": _serialize_tool_state(tools.preview),
            }
        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        if series is None:
            return {
                "scope_type": scope_type,
                "series_id": series_id,
                "error": "series_not_found",
            }
        return {
            "scope_type": scope_type,
            "series_id": series_id,
            "series_title": series.title,
            "video_count": len(series.videos),
        }


def _build_default_embed_model(root_dir: Path | None):
    if root_dir is None:
        return MockEmbedding(embed_dim=32)
    apply_runtime_env_overrides(root_dir)
    settings = load_settings(root_dir / "config" / "settings.toml", root_dir)
    retrieval_settings = settings.agent_retrieval
    local_embedding_dir = root_dir / "data" / "models" / "huggingface" / "bge-base-zh-v1.5"
    if retrieval_settings.embedding_model == "BAAI/bge-base-zh-v1.5" and local_embedding_dir.is_dir():
        from dataclasses import replace

        retrieval_settings = replace(
            retrieval_settings,
            embedding_model=str(local_embedding_dir),
        )
    return _build_embed_model_from_settings(
        retrieval_settings=retrieval_settings,
    )


def _build_embed_model_from_settings(*, retrieval_settings: AgentRetrievalSettings):
    if retrieval_settings.embedding_provider == "local_huggingface":
        return _build_local_huggingface_embedding(retrieval_settings)
    raise ValueError(
        f"Unsupported embedding provider: {retrieval_settings.embedding_provider}"
    )


def _build_local_huggingface_embedding(
    retrieval_settings: AgentRetrievalSettings,
):
    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    except ImportError as exc:
        raise RuntimeError(
            "缺少本地 embedding 依赖。请安装 `llama-index-embeddings-huggingface` 和 `sentence-transformers`。"
        ) from exc

    resolved_device = _resolve_embedding_device(retrieval_settings.embedding_device)
    try:
        return HuggingFaceEmbedding(
            model_name=retrieval_settings.embedding_model,
            device=resolved_device,
            embed_batch_size=retrieval_settings.embedding_batch_size,
        )
    except Exception as exc:
        if resolved_device != "cpu" and _looks_like_torch_cuda_error(exc):
            raise RuntimeError(
                "当前向量检索配置为 GPU，但当前 PyTorch 环境未启用 CUDA。"
                "请安装支持 CUDA 的 PyTorch，或将 config/settings.toml 中"
                " [agent_retrieval].embedding_device 改为 \"cpu\"。"
            ) from exc
        raise


def _resolve_embedding_device(device: str) -> str:
    normalized = (device or "cpu").strip().lower()
    if normalized == "auto":
        return "cuda" if _torch_cuda_available() else "cpu"
    if normalized == "gpu":
        return "cuda"
    return normalized


def _torch_cuda_available() -> bool:
    try:
        import torch
    except Exception:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _looks_like_torch_cuda_error(error: BaseException) -> bool:
    message = str(error).lower()
    if "torch not compiled with cuda enabled" in message:
        return True
    if "cuda" in message and "not available" in message:
        return True
    current = error.__cause__ or error.__context__
    if current is not None and current is not error:
        return _looks_like_torch_cuda_error(current)
    return False


def _build_filters(
    *,
    scope_type: str,
    series_id: str,
    video_id: str,
    target_source: str,
    source_tags: list[str],
) -> MetadataFilters:
    filters: list[MetadataFilter | MetadataFilters] = [
        MetadataFilter(key="series_id", value=series_id),
    ]
    if scope_type == "video":
        filters.append(MetadataFilter(key="video_id", value=video_id))
    family_filters = _build_source_family_filters(source_tags, target_source=target_source)
    if family_filters:
        if len(family_filters) == 1:
            filters.append(family_filters[0])
        else:
            filters.append(MetadataFilters(filters=family_filters, condition=FilterCondition.OR))
    return MetadataFilters(filters=filters, condition=FilterCondition.AND)


def _build_source_family_filters(
    source_tags: list[str],
    *,
    target_source: str,
) -> list[MetadataFilter]:
    if source_tags:
        families = []
        for tag in source_tags:
            if tag == "summary":
                families.append("summary")
            elif tag == "transcript":
                families.append("transcript")
            elif tag == "notes":
                families.append("notes")
            elif tag == "cards":
                families.append("cards")
        if families:
            unique_families = list(dict.fromkeys(families))
            if len(unique_families) == 1:
                return [MetadataFilter(key="source_family", value=unique_families[0])]
            return [
                MetadataFilter(
                    key="source_family",
                    value=unique_families,
                    operator=FilterOperator.IN,
                )
            ]
    if target_source == "summary":
        return [MetadataFilter(key="source_family", value="summary")]
    if target_source == "transcript":
        return [MetadataFilter(key="source_family", value="transcript")]
    return []


def _build_series_signatures(workspace: VideoLibraryReader) -> SeriesSignatureMap:
    signatures: SeriesSignatureMap = {}
    for series in workspace.list_series():
        signatures[series.id] = _build_series_signature(workspace, series.id)
    return signatures


def _build_series_signature(workspace: VideoLibraryReader, series_id: str) -> SeriesSignature:
    series = next((item for item in workspace.list_series() if item.id == series_id), None)
    if series is None:
        return ()
    video_parts: list[str] = []
    for video in series.videos:
        summary = workspace.get_video_summary(series.id, video.id)
        transcript = workspace.get_video_transcript(series.id, video.id)
        notes = workspace.get_video_notes(series.id, video.id)
        cards = workspace.get_video_knowledge_cards(series.id, video.id)
        summary_hash = _artifact_fingerprint(summary)
        transcript_hash = _artifact_fingerprint(transcript)
        notes_hash = _artifact_fingerprint(notes)
        cards_hash = _artifact_fingerprint(cards)
        video_parts.append(
            f"{series.id}:{video.id}:{video.status}:{int(video.processed)}:"
            f"{summary_hash}:{transcript_hash}:{notes_hash}:{cards_hash}"
        )
    return tuple(sorted(video_parts))


def _build_workspace_signature(workspace: VideoLibraryReader) -> tuple[tuple[str, ...], tuple[str, ...]]:
    signatures = _build_series_signatures(workspace)
    return tuple(sorted(signatures)), tuple(sorted(item for signature in signatures.values() for item in signature))


def _artifact_fingerprint(value: object) -> str:
    if value is None:
        return "0"
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def _build_documents(workspace: VideoLibraryReader) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    for series in workspace.list_series():
        documents.extend(_build_documents_for_series(workspace, series_id=series.id))
    return documents


def _build_documents_for_series(
    workspace: VideoLibraryReader,
    *,
    series_id: str,
) -> list[RetrievalDocument]:
    series = next((item for item in workspace.list_series() if item.id == series_id), None)
    if series is None:
        return []
    documents: list[RetrievalDocument] = []
    for video in series.videos:
        documents.extend(_build_documents_for_video(workspace, series_id=series.id, video_id=video.id))
    return documents


def _build_documents_for_video(
    workspace: VideoLibraryReader,
    *,
    series_id: str,
    video_id: str,
) -> list[RetrievalDocument]:
    return _build_documents_for_assets(
        summary=workspace.get_video_summary(series_id, video_id),
        transcript=workspace.get_video_transcript(series_id, video_id),
        notes=workspace.get_video_notes(series_id, video_id),
        knowledge_cards=workspace.get_video_knowledge_cards(series_id, video_id),
    )


def _build_documents_for_assets(
    *,
    summary,
    transcript,
    notes,
    knowledge_cards,
) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    if summary is not None:
        documents.extend(_build_summary_documents(summary))
    if transcript is not None:
        documents.extend(_build_transcript_documents(transcript))
    if notes is not None:
        documents.extend(_build_notes_documents(notes))
    if knowledge_cards is not None:
        documents.extend(_build_knowledge_card_documents(knowledge_cards))
    return documents


def _to_llama_documents(documents: list[RetrievalDocument]) -> list[Document]:
    return [
        Document(
            id_=str(document.metadata["doc_id"]),
            text=document.text,
            metadata=document.metadata,
        )
        for document in documents
    ]


def _build_summary_documents(summary) -> list[RetrievalDocument]:
    payload = summary.summary
    docs: list[RetrievalDocument] = []
    summary_text = "\n".join(
        part
        for part in [
            str(payload.get("one_sentence_summary", "")).strip(),
            str(payload.get("core_problem", "")).strip(),
            "\n".join(
                item.strip()
                for item in payload.get("key_takeaways", [])
                if isinstance(item, str) and item.strip()
            ),
        ]
        if part
    )
    if summary_text:
        docs.append(
            RetrievalDocument(
                text=summary_text,
                metadata=_with_common_metadata(
                    {
                    "doc_id": f"series:{summary.series_id}:video:{summary.video_id}:summary_global",
                    "series_id": summary.series_id,
                    "video_id": summary.video_id,
                    "title": summary.title,
                    "source_type": "summary_global",
                    "source_family": "summary",
                    }
                ),
            )
        )
    for chapter in payload.get("chapters", []):
        if not isinstance(chapter, dict):
            continue
        chapter_text = "\n".join(
            part
            for part in [
                str(chapter.get("title", "")).strip(),
                str(chapter.get("summary", "")).strip(),
                "\n".join(
                    item.strip()
                    for item in chapter.get("key_points", [])
                    if isinstance(item, str) and item.strip()
                ),
            ]
            if part
        )
        if not chapter_text:
            continue
        docs.append(
            RetrievalDocument(
                text=chapter_text,
                metadata=_with_common_metadata(
                    {
                    "doc_id": f"series:{summary.series_id}:video:{summary.video_id}:summary_chapter:{str(chapter.get('id', '')).strip() or str(chapter.get('title', '')).strip()}",
                    "series_id": summary.series_id,
                    "video_id": summary.video_id,
                    "title": summary.title,
                    "source_type": "summary_chapter",
                    "source_family": "summary",
                    "chapter_title": str(chapter.get("title", "")).strip(),
                    "start_seconds": chapter.get("start_seconds"),
                    "end_seconds": chapter.get("end_seconds"),
                    }
                ),
            )
        )
    return docs


def _build_transcript_documents(transcript) -> list[RetrievalDocument]:
    docs: list[RetrievalDocument] = []
    for segment in transcript.segments:
        docs.append(
            RetrievalDocument(
                text=segment.text,
                metadata=_with_common_metadata(
                    {
                    "doc_id": f"series:{transcript.series_id}:video:{transcript.video_id}:transcript:{segment.start_seconds}-{segment.end_seconds}",
                    "series_id": transcript.series_id,
                    "video_id": transcript.video_id,
                    "title": transcript.title,
                    "source_type": "transcript_chunk",
                    "source_family": "transcript",
                    "start_seconds": segment.start_seconds,
                    "end_seconds": segment.end_seconds,
                    }
                ),
            )
        )
    return docs


def _build_notes_documents(notes) -> list[RetrievalDocument]:
    docs: list[RetrievalDocument] = []
    for note in notes.notes:
        note_text = "\n".join(
            part
            for part in [
                str(note.title).strip(),
                str(note.content).strip(),
            ]
            if part
        ).strip()
        if not note_text:
            continue
        docs.append(
            RetrievalDocument(
                text=note_text,
                metadata=_with_common_metadata(
                    {
                    "doc_id": f"series:{notes.series_id}:video:{notes.video_id}:note:{note.id}",
                    "series_id": notes.series_id,
                    "video_id": notes.video_id,
                    "title": notes.title,
                    "source_type": "note",
                    "source_family": "notes",
                    "note_id": note.id,
                    "note_source": note.source,
                    }
                ),
            )
        )
    return docs


def _build_knowledge_card_documents(cards) -> list[RetrievalDocument]:
    docs: list[RetrievalDocument] = []
    for card in cards.cards:
        card_text = "\n".join(
            part
            for part in [
                str(card.title).strip(),
                str(card.summary).strip(),
                str(card.details).strip(),
                " ".join(keyword.strip() for keyword in card.keywords if isinstance(keyword, str) and keyword.strip()),
            ]
            if part
        ).strip()
        if not card_text:
            continue
        docs.append(
            RetrievalDocument(
                text=card_text,
                metadata=_with_common_metadata(
                    {
                    "doc_id": f"series:{cards.series_id}:video:{cards.video_id}:knowledge_card:{card.id}",
                    "series_id": cards.series_id,
                    "video_id": cards.video_id,
                    "title": cards.title,
                    "source_type": "knowledge_card",
                    "source_family": "cards",
                    "card_id": card.id,
                    "card_kind": card.kind,
                    }
                ),
            )
        )
    return docs


def _with_common_metadata(metadata: dict[str, object]) -> dict[str, object]:
    merged = dict(COMMON_METADATA_DEFAULTS)
    merged.update(metadata)
    for key in ("chapter_title", "note_id", "note_source", "card_id", "card_kind"):
        if merged.get(key) is None:
            merged[key] = ""
    return merged


def _reset_lancedb_table(db_uri: str, table_name: str) -> None:
    connection = lancedb.connect(db_uri)
    try:
        connection.drop_table(table_name)
    except Exception:
        # table 不存在时直接忽略，后续会重建
        pass


def _delete_rows(*, db_uri: str, table_name: str, where: str) -> None:
    connection = lancedb.connect(db_uri)
    table = connection.open_table(table_name)
    table.delete(where)


def _optimize_lancedb_table(db_uri: str, table_name: str) -> None:
    connection = lancedb.connect(db_uri)
    table = connection.open_table(table_name)
    table.optimize(cleanup_older_than=LANCEDB_OPTIMIZE_CLEANUP_OLDER_THAN)


def _table_exists(db_uri: str, table_name: str) -> bool:
    connection = lancedb.connect(db_uri)
    try:
        table_names = set(connection.table_names())
    except Exception:
        return False
    return table_name in table_names


def _escape_lance_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _signature_file_path(db_uri: str, table_name: str) -> Path:
    return Path(db_uri) / f"{table_name}.signature.json"


def _write_signature_file(
    db_uri: str,
    table_name: str,
    signature: SeriesSignatureMap,
) -> None:
    signature_path = _signature_file_path(db_uri, table_name)
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        signature_path,
        json.dumps(
            {
                "index_schema_version": INDEX_SCHEMA_VERSION,
                "series_signatures": {
                    series_id: list(series_signature)
                    for series_id, series_signature in sorted(signature.items())
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


def _read_signature_file(
    db_uri: str,
    table_name: str,
) -> SeriesSignatureMap | None:
    signature_path = _signature_file_path(db_uri, table_name)
    if not signature_path.exists():
        return None
    try:
        payload = json.loads(signature_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    raw_series_signatures = payload.get("series_signatures")
    if isinstance(raw_series_signatures, dict):
        signatures: SeriesSignatureMap = {}
        for series_id, raw_signature in raw_series_signatures.items():
            if not isinstance(raw_signature, list):
                return None
            signatures[str(series_id)] = tuple(str(item) for item in raw_signature)
        return signatures
    raw_signature = payload.get("signature")
    if (
        not isinstance(raw_signature, list)
        or len(raw_signature) != 2
        or not isinstance(raw_signature[0], list)
        or not isinstance(raw_signature[1], list)
    ):
        return None
    return _series_signatures_from_legacy_workspace_signature(
        tuple(str(item) for item in raw_signature[0]),
        tuple(str(item) for item in raw_signature[1]),
    )


def _series_signatures_from_legacy_workspace_signature(
    series_ids: tuple[str, ...],
    video_parts: tuple[str, ...],
) -> SeriesSignatureMap:
    signatures: SeriesSignatureMap = {series_id: () for series_id in series_ids}
    grouped_parts: dict[str, list[str]] = {series_id: [] for series_id in series_ids}
    for part in video_parts:
        series_id = part.split(":", 1)[0]
        grouped_parts.setdefault(series_id, []).append(part)
    for series_id, parts in grouped_parts.items():
        signatures[series_id] = tuple(sorted(parts))
    return signatures


def _expand_transcript_hit(
    *,
    workspace: VideoLibraryReader,
    series_id: str,
    video_id: str,
    hit: dict[str, object],
    context_window_seconds: int,
) -> dict[str, object]:
    transcript = workspace.get_video_transcript(series_id, video_id)
    if transcript is None:
        return hit
    start = float(hit.get("start_seconds") or 0.0) - context_window_seconds
    end = float(hit.get("end_seconds") or 0.0) + context_window_seconds
    segments = [
        segment
        for segment in transcript.segments
        if not (segment.end_seconds < start or segment.start_seconds > end)
    ]
    if not segments:
        return hit
    return {
        **hit,
        "start_seconds": segments[0].start_seconds,
        "end_seconds": segments[-1].end_seconds,
        "text": " ".join(segment.text for segment in segments),
        "snippet": " ".join(segment.text for segment in segments),
    }


def _serialize_tool_state(tool) -> dict[str, object]:
    return {
        "id": tool.id,
        "title": tool.title,
        "available": tool.available,
        "generated": tool.generated,
        "status": tool.status,
    }
