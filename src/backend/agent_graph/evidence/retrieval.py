from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import lancedb
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.vector_stores import FilterCondition, FilterOperator, MetadataFilter, MetadataFilters
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from backend.video_summary.infrastructure.settings import (
    AgentRetrievalSettings,
    load_settings,
)
from backend.video_summary.library.ports import VideoWorkspace

INDEX_SCHEMA_VERSION = 3
INDEX_TABLE_NAME = f"agent_graph_evidence_v{INDEX_SCHEMA_VERSION}"
COMMON_METADATA_DEFAULTS: dict[str, object] = {
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

    def invalidate(self) -> None:
        self._index = None
        self._signature = None
        _reset_lancedb_table(self._db_uri, INDEX_TABLE_NAME)

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
                source_tags=source_tags or [],
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
            "source_tags": list(source_tags or []),
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
        _reset_lancedb_table(self._db_uri, INDEX_TABLE_NAME)
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


def _build_workspace_signature(workspace: VideoWorkspace) -> tuple[tuple[str, ...], tuple[str, ...]]:
    series_parts: list[str] = []
    video_parts: list[str] = []
    for series in workspace.list_series():
        series_parts.append(series.id)
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
    return tuple(sorted(series_parts)), tuple(sorted(video_parts))


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


def _build_documents(workspace: VideoWorkspace) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    for series in workspace.list_series():
        for video in series.videos:
            summary = workspace.get_video_summary(series.id, video.id)
            transcript = workspace.get_video_transcript(series.id, video.id)
            notes = workspace.get_video_notes(series.id, video.id)
            knowledge_cards = workspace.get_video_knowledge_cards(series.id, video.id)
            if summary is not None:
                documents.extend(_build_summary_documents(summary))
            if transcript is not None:
                documents.extend(_build_transcript_documents(transcript))
            if notes is not None:
                documents.extend(_build_notes_documents(notes))
            if knowledge_cards is not None:
                documents.extend(_build_knowledge_card_documents(knowledge_cards))
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
                metadata=_with_common_metadata(
                    {
                    "series_id": summary.series_id,
                    "video_id": summary.video_id,
                    "title": summary.title,
                    "source_type": "summary",
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
                    "series_id": summary.series_id,
                    "video_id": summary.video_id,
                    "title": summary.title,
                    "source_type": "chapter",
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
        first_ref = card.source_refs[0] if card.source_refs else None
        docs.append(
            RetrievalDocument(
                text=card_text,
                metadata=_with_common_metadata(
                    {
                    "series_id": cards.series_id,
                    "video_id": cards.video_id,
                    "title": cards.title,
                    "source_type": "knowledge_card",
                    "source_family": "cards",
                    "card_id": card.id,
                    "card_kind": card.kind,
                    "start_seconds": getattr(first_ref, "start_seconds", None),
                    "end_seconds": getattr(first_ref, "end_seconds", None),
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
