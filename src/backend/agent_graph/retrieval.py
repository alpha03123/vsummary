from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.vector_stores import FilterCondition, MetadataFilter, MetadataFilters
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from backend.video_summary.infrastructure.settings import (
    AgentRetrievalSettings,
    load_settings,
)
from backend.video_summary.library.ports import VideoWorkspace


@dataclass(frozen=True)
class RetrievalDocument:
    text: str
    metadata: dict[str, object]


class SeriesRetrievalService:
    def __init__(
        self,
        *,
        workspace: VideoWorkspace,
        db_uri: str,
        embed_model=None,
        root_dir: Path | None = None,
    ) -> None:
        self._workspace = workspace
        self._db_uri = db_uri
        self._embed_model = embed_model or _build_default_embed_model(root_dir)
        self._index: VectorStoreIndex | None = None
        self._signature: tuple[tuple[str, ...], tuple[str, ...]] | None = None

    def search(
        self,
        *,
        scope_type: str,
        series_id: str,
        video_id: str,
        query: str,
        target_source: str,
        expand_context: bool,
        context_window_seconds: int,
        max_hits: int,
    ) -> dict[str, object]:
        index = self._get_or_build_index()
        retriever = index.as_retriever(
            similarity_top_k=max(8, max_hits * 4),
            filters=_build_filters(
                scope_type=scope_type,
                series_id=series_id,
                video_id=video_id,
                target_source=target_source,
            ),
        )
        nodes = retriever.retrieve(query)
        hits: list[dict[str, object]] = []
        for item in nodes:
            metadata = dict(getattr(item.node, "metadata", {}) or {})
            hit = {
                "video_id": str(metadata.get("video_id", "")),
                "title": str(metadata.get("title", "")),
                "source_type": str(metadata.get("source_type", "")),
                "score": float(item.score or 0.0),
                "start_seconds": metadata.get("start_seconds"),
                "end_seconds": metadata.get("end_seconds"),
                "chapter_title": metadata.get("chapter_title"),
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

        hits.sort(key=lambda item: (-float(item["score"]), str(item["video_id"]), str(item["source_type"])))
        return {
            "scope_type": scope_type,
            "series_id": series_id,
            "video_id": video_id,
            "query": query,
            "target_source": target_source,
            "hits": hits[:max_hits],
        }

    def _get_or_build_index(self) -> VectorStoreIndex:
        signature = _build_workspace_signature(self._workspace)
        if self._index is not None and self._signature == signature:
            return self._index

        documents = [
            Document(text=document.text, metadata=document.metadata)
            for document in _build_documents(self._workspace)
        ]
        vector_store = LanceDBVectorStore(
            uri=self._db_uri,
            table_name="agent_graph_evidence",
            mode="overwrite",
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        self._index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            embed_model=self._embed_model,
            show_progress=False,
        )
        self._signature = signature
        return self._index


class MetaStateReader:
    def __init__(self, *, workspace: VideoWorkspace) -> None:
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
    settings = load_settings(root_dir / "config" / "settings.toml", root_dir)
    return _build_embed_model_from_settings(
        retrieval_settings=settings.agent_retrieval,
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

    return HuggingFaceEmbedding(
        model_name=retrieval_settings.embedding_model,
        device=retrieval_settings.embedding_device,
        embed_batch_size=retrieval_settings.embedding_batch_size,
    )


def _build_filters(
    *,
    scope_type: str,
    series_id: str,
    video_id: str,
    target_source: str,
) -> MetadataFilters:
    filters: list[MetadataFilter | MetadataFilters] = [
        MetadataFilter(key="series_id", value=series_id),
    ]
    if scope_type == "video":
        filters.append(MetadataFilter(key="video_id", value=video_id))
    if target_source == "summary":
        filters.append(MetadataFilter(key="source_family", value="summary"))
    elif target_source == "transcript":
        filters.append(MetadataFilter(key="source_family", value="transcript"))
    return MetadataFilters(filters=filters, condition=FilterCondition.AND)


def _build_workspace_signature(workspace: VideoWorkspace) -> tuple[tuple[str, ...], tuple[str, ...]]:
    series_parts: list[str] = []
    video_parts: list[str] = []
    for series in workspace.list_series():
        series_parts.append(series.id)
        for video in series.videos:
            video_parts.append(f"{series.id}:{video.id}:{video.status}:{int(video.processed)}")
    return tuple(sorted(series_parts)), tuple(sorted(video_parts))


def _build_documents(workspace: VideoWorkspace) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    for series in workspace.list_series():
        for video in series.videos:
            summary = workspace.get_video_summary(series.id, video.id)
            transcript = workspace.get_video_transcript(series.id, video.id)
            if summary is not None:
                documents.extend(_build_summary_documents(summary))
            if transcript is not None:
                documents.extend(_build_transcript_documents(transcript))
    return documents


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
                metadata={
                    "series_id": summary.series_id,
                    "video_id": summary.video_id,
                    "title": summary.title,
                    "source_type": "summary",
                    "source_family": "summary",
                },
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
                metadata={
                    "series_id": summary.series_id,
                    "video_id": summary.video_id,
                    "title": summary.title,
                    "source_type": "chapter",
                    "source_family": "summary",
                    "chapter_title": str(chapter.get("title", "")).strip(),
                    "start_seconds": chapter.get("start_seconds"),
                    "end_seconds": chapter.get("end_seconds"),
                },
            )
        )
    return docs


def _build_transcript_documents(transcript) -> list[RetrievalDocument]:
    docs: list[RetrievalDocument] = []
    for segment in transcript.segments:
        docs.append(
            RetrievalDocument(
                text=segment.text,
                metadata={
                    "series_id": transcript.series_id,
                    "video_id": transcript.video_id,
                    "title": transcript.title,
                    "source_type": "transcript_chunk",
                    "source_family": "transcript",
                    "start_seconds": segment.start_seconds,
                    "end_seconds": segment.end_seconds,
                },
            )
        )
    return docs


def _expand_transcript_hit(
    *,
    workspace: VideoWorkspace,
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
