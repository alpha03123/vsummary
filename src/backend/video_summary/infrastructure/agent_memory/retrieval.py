"""Agent RAG 检索服务（SeriesRetrievalService）与文档构建工具集合。

本模块是 RAG 子系统的核心：
- `SeriesRetrievalService`：管理 LanceDB 上的 RAG 索引并对外提供检索；
  支持全量刷新、单视频 upsert、按系列/视频删除，以及基于 LanceDB
  metadata 过滤的混合检索（可选 BGE 重排序）；
- `MetaStateReader`：把工作区内的视频/系列元数据序列化成 Agent 工具
  可直接消费的字典；
- 一组内部辅助函数负责把工作区制品（总结、转写、笔记、知识卡）转写为
  `RetrievalDocument` 并按 series signature 维持增量一致性。
"""

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
from backend.video_summary.infrastructure.agent_memory.fastembed_adapter import build_fastembed_embedding
from backend.video_summary.library.ports import VideoLibraryReader

INDEX_SCHEMA_VERSION = 5
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
    """写入 LanceDB 的一条检索文档（`text` + `metadata` 的不可变组合）。

    Attributes:
        text: 被嵌入与检索的正文。
        metadata: 与文档一同写入 LanceDB 的 metadata（用于过滤与引用回溯）。
    """

    text: str
    metadata: dict[str, object]


class SeriesRetrievalService:
    """工作区级 RAG 检索服务（基于 LanceDB + LlamaIndex）。

    业务目的：在 series scope 下回答用户问题时，先从工作区所有视频的总结/
    转写/笔记/知识卡中召回相关证据片段，并按需附上时间戳、章节标题等引用
    信息供前端回放与证据展示使用。

    关键不变量：
        - 索引 schema 版本由 `INDEX_SCHEMA_VERSION` 控制；表名
          `INDEX_TABLE_NAME` 携带版本号，跨版本天然隔离；
        - 每次索引变更后会同步更新 `*.signature.json`，用于在 `search` 时
          检测"工作区内容已变化但索引未刷新"，避免返回陈旧结果；
        - 写入/删除均通过 `self._index_lock`（`RLock`）串行化，保证并发安全；
        - `search` 走的是 `_require_index` 兜底链：未构建则尝试加载持久化
          索引；都拿不到则触发 `refresh_series` 并最终要求调用方先做刷新。
    """

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
        """注入工作区读取端口、数据库 URI、embedding/重排序模型与配置目录。

        Args:
            workspace: 用于读取总结/转写/笔记/知识卡等制品。
            db_uri: LanceDB 数据库目录 URI。
            embed_model: 可选的 embedding 模型；为 `None` 时根据 `root_dir`
                自动构造（默认走 `fastembed`/`BAAI/bge-small-zh-v1.5`）。
            reranker: 可选的语义重排序打分器（实现 `SemanticScorer`）。
            rerank_enabled: 重排序开关显式覆盖；为 `None` 时读 settings.toml 默认值。
            root_dir: 项目根目录；为 `None` 时使用默认 embedding 与默认运行时设置。
        """
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
        """丢弃内存中的索引与 signature 缓存，迫使下一次访问重新构建/加载。"""
        with self._index_lock:
            self._index = None
            self._series_signatures = None

    def refresh(self) -> None:
        """`refresh_all` 的便捷别名，用于与 `WorkspaceIndexRefresher` 接口对齐。"""
        self.refresh_all()

    def refresh_all(self) -> None:
        """全量重建工作区级 RAG 索引（清空 LanceDB 表并按当前工作区内容重新写入）。"""
        with self._index_lock:
            self._index = None
            self._series_signatures = None
            self._rebuild_index()

    def refresh_series(self, series_id: str) -> None:
        """重建指定系列的索引行（不影响其他系列）。

        若目标表尚未创建则用 `overwrite` 模式写入；否则先按 series 删除
        再以 `append` 模式补回。最终刷新该系列的 signature 并触发缓存失效。

        Args:
            series_id: 目标系列 ID。
        """
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
        """把单个视频的制品加入或更新到 RAG 索引（增量 upsert）。

        若索引尚未具备增量条件（表不存在或 signature 缺失），自动降级为
        整系列重建；否则先删除该视频的旧行，再追加新生成的文档并更新
        signature。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
        """
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
        """从 RAG 索引中删除单个视频的全部行，索引未就绪时降级为整系列重建。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
        """
        with self._index_lock:
            if not self._is_incremental_mutation_ready():
                self.refresh_series(series_id)
                return
            self._delete_video_rows(series_id=series_id, video_id=video_id)
            self._finalize_incremental_mutation(series_id)

    def delete_series(self, series_id: str) -> None:
        """从 RAG 索引中删除整个系列的所有行，并尝试对 LanceDB 表做合并清理。

        Args:
            series_id: 目标系列 ID。
        """
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
        """对查询执行 RAG 检索并返回排序后的证据列表。

        处理流程：
            1. 在锁内确保索引已加载/已刷新；
            2. 根据 scope_type/series_id/video_id/target_source/source_tags
               构建 LlamaIndex MetadataFilters；
            3. 调用 retriever 召回 `max_hits * RERANK_EMBEDDING_MULTIPLIER`
               条候选（启用 rerank 时放大 4 倍）；
            4. 对转写类命中按 `context_window_seconds` 扩展窗口文本；
            5. 可选用 BGE reranker 重排；最终截取 top-K 并附 `evidence_id`。

        Args:
            scope_type: 检索作用域（`series` / `video`）。
            series_id: 所属系列 ID。
            video_id: 视频 ID（`scope_type == "video"` 时参与过滤）。
            query: 用户查询字符串。
            target_source: 主来源（`summary` / `transcript` / 其他），
                影响 source_family 默认过滤。
            source_tags: 额外来源标签（`summary` / `transcript` / `notes` /
                `cards`），为空时按 `target_source` 推导。
            expand_context: 是否对转写命中按窗口扩展前后文。
            context_window_seconds: 转写命中扩展窗口的秒数。
            max_hits: 最大返回命中数；为 `None` 时读 settings 默认值。

        Returns:
            含 `hits` 列表与查询上下文的字典；每条 hit 含 `doc_id` /
            `video_id` / `title` / `source_type` / `start_seconds` /
            `end_seconds` / `score` / `text` / `evidence_id` 等字段。
        """
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
        """返回 settings 中配置的默认 `max_hits`（供接口对外暴露）。"""
        return self._load_runtime_retrieval_settings().max_hits

    def _get_or_build_index(self) -> VectorStoreIndex:
        """按"signature 没变则复用，有变则重建"的策略返回可用索引。

        流程：先比内存里缓存的 `series_signatures`，未命中再尝试从 LanceDB
        加载现有索引，失败则触发 `_rebuild_index`。
        """
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
        """保证检索时可拿到一个已加载索引；若 signature 过陈旧则异步刷新该系列。

        任何路径下若表与索引都不可用，最终会抛 `RuntimeError` 提示先做刷新。
        """
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
        """以 `overwrite` 模式重建 LanceDB 表并生成新的签名快照。"""
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
        """以 `append` 模式把文档追加到 LanceDB（封装 `_write_documents`）。"""
        self._write_documents(documents, mode="append")

    def _write_documents(self, documents: list[RetrievalDocument], *, mode: str) -> None:
        """把 `RetrievalDocument` 列表按指定 mode 写入 LanceDB 表。"""
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
        """判断索引是否处于"可增量写入"状态（表存在且 signature 文件已落盘）。"""
        return (
            _table_exists(self._db_uri, INDEX_TABLE_NAME)
            and _read_signature_file(self._db_uri, INDEX_TABLE_NAME) is not None
        )

    def _finalize_incremental_mutation(self, series_id: str) -> None:
        """一次增量写入完成后：失效缓存并按当前工作区内容回写该系列 signature。"""
        self.invalidate()
        signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
        current_signature = _build_series_signature(self._workspace, series_id)
        if current_signature:
            signatures[series_id] = current_signature
        else:
            signatures.pop(series_id, None)
        _write_signature_file(self._db_uri, INDEX_TABLE_NAME, signatures)

    def _write_series_signature(self, series_id: str) -> None:
        """按当前工作区内容刷新指定系列的 signature（不改动缓存）。"""
        signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
        current_signature = _build_series_signature(self._workspace, series_id)
        if current_signature:
            signatures[series_id] = current_signature
        else:
            signatures.pop(series_id, None)
        _write_signature_file(self._db_uri, INDEX_TABLE_NAME, signatures)

    def _remove_series_signature(self, series_id: str) -> None:
        """把指定系列从 signature 文件中移除（用于表未就绪时的 fallback 删除）。"""
        signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
        signatures.pop(series_id, None)
        _write_signature_file(self._db_uri, INDEX_TABLE_NAME, signatures)

    def _is_series_signature_stale(self, series_id: str) -> bool:
        """判断指定系列的 signature 是否已陈旧（与工作区当前内容不一致）。

        `series_id` 为空时返回 `False`，避免对未知 scope 误触发刷新。
        """
        if not series_id:
            return False
        stored_signatures = self._series_signatures
        if stored_signatures is None:
            stored_signatures = _read_signature_file(self._db_uri, INDEX_TABLE_NAME) or {}
            self._series_signatures = stored_signatures
        return stored_signatures.get(series_id) != _build_series_signature(self._workspace, series_id)

    def _refresh_series_async(self, series_id: str) -> None:
        """以守护线程异步刷新指定系列的索引（异常仅记录日志、不上抛）。"""
        if not series_id:
            return

        def refresh() -> None:
            try:
                self.refresh_series(series_id)
            except Exception:
                LOGGER.exception("series index refresh failed for %s", series_id)

        Thread(target=refresh, daemon=True).start()

    def _delete_video_rows(self, *, series_id: str, video_id: str) -> None:
        """按 series_id + video_id 精确删除 LanceDB 表中的若干行。"""
        _delete_rows(
            db_uri=self._db_uri,
            table_name=INDEX_TABLE_NAME,
            where=(
                f"metadata.series_id = '{_escape_lance_string(series_id)}' "
                f"and metadata.video_id = '{_escape_lance_string(video_id)}'"
            ),
        )

    def _delete_series_rows(self, *, series_id: str) -> None:
        """按 series_id 删除 LanceDB 表中的所有匹配行。"""
        _delete_rows(
            db_uri=self._db_uri,
            table_name=INDEX_TABLE_NAME,
            where=f"metadata.series_id = '{_escape_lance_string(series_id)}'",
        )

    def _try_load_existing_index(self) -> VectorStoreIndex | None:
        """尝试把 LanceDB 表包装为 LlamaIndex 索引；表不存在时返回 `None`。"""
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
        """把外部 `max_hits` 与运行时默认值归并为最终生效值；<=0 视为非法。"""
        if max_hits is not None:
            if max_hits <= 0:
                raise ValueError("max_hits 必须是正整数。")
            return max_hits
        return self.default_max_hits()

    def _resolve_rerank_enabled(self) -> bool:
        """返回当前生效的 rerank 开关：构造参数 > settings.toml 默认值。"""
        if self._rerank_enabled_override is not None:
            return self._rerank_enabled_override
        return self._load_runtime_retrieval_settings().rerank_enabled

    def _load_runtime_retrieval_settings(self) -> AgentRetrievalSettings:
        """读取 settings.toml 中 `agent_retrieval` 段；`root_dir` 缺失时返回内置默认值。"""
        if self._root_dir is None:
            return AgentRetrievalSettings(
                embedding_provider="fastembed",
                embedding_model="BAAI/bge-small-zh-v1.5",
                embedding_device="cpu",
                embedding_batch_size=8,
                max_hits=DEFAULT_AGENT_RETRIEVAL_MAX_HITS,
                rerank_enabled=DEFAULT_AGENT_RETRIEVAL_RERANK_ENABLED,
            )
        return load_settings(self._root_dir / "config" / "settings.toml", self._root_dir).agent_retrieval


class MetaStateReader:
    """把工作区内的"工具状态"序列化为 Agent 工具可直接消费的字典。

    业务目的：在 series/video scope 下回答关于"工作区里有哪些工具及其状态"
    的问题时，让 LLM 能基于结构化字典判断下一步动作，而不是读原始 JSON。
    """

    def __init__(self, *, workspace: VideoLibraryReader) -> None:
        """注入工作区读取端口。"""
        self._workspace = workspace

    def read(self, *, scope_type: str, series_id: str, video_id: str) -> dict[str, object]:
        """读取并序列化指定 scope 的工具状态。

        Args:
            scope_type: `video` 时取该视频的工具栏；其他值视为 series，
                返回 series 级概览（标题与视频数量）。
            series_id: 所属系列 ID。
            video_id: 视频 ID（仅 `scope_type == "video"` 时使用）。

        Returns:
            `video` scope 返回 `overview`/`knowledge_cards`/`mindmap`/`notes`/
            `preview` 五个工具状态；系列或视频缺失时返回含 `error` 字段的字典。
        """
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
    """根据 `root_dir` 构造默认 embedding 模型。

    `root_dir` 为 `None` 时返回 32 维 `MockEmbedding`（便于无配置环境快速启动）；
    否则按 settings.toml 的 `agent_retrieval` 段构造 FastEmbed embedding。
    """
    if root_dir is None:
        return MockEmbedding(embed_dim=32)
    apply_runtime_env_overrides(root_dir)
    settings = load_settings(root_dir / "config" / "settings.toml", root_dir)
    return _build_embed_model_from_settings(
        retrieval_settings=settings.agent_retrieval,
        cache_dir=root_dir / "data" / "models" / "fastembed",
    )


def _build_embed_model_from_settings(
    *,
    retrieval_settings: AgentRetrievalSettings,
    cache_dir: Path | None = None,
):
    """把 settings 里的 `AgentRetrievalSettings` 转成实际 embedding 模型。

    当前仅支持 `fastembed` provider；其他 provider 抛 `ValueError`。
    """
    if retrieval_settings.embedding_provider == "fastembed":
        return build_fastembed_embedding(
            model_name=retrieval_settings.embedding_model,
            device=retrieval_settings.embedding_device,
            embed_batch_size=retrieval_settings.embedding_batch_size,
            cache_dir=str(cache_dir) if cache_dir is not None else None,
        )
    raise ValueError(
        f"Unsupported embedding provider: {retrieval_settings.embedding_provider}"
    )


def _build_filters(
    *,
    scope_type: str,
    series_id: str,
    video_id: str,
    target_source: str,
    source_tags: list[str],
) -> MetadataFilters:
    """根据 scope/来源组装 LlamaIndex MetadataFilters。

    规则：
        - 始终按 series_id 过滤；
        - `scope_type == "video"` 时再追加 video_id 过滤；
        - 根据 `source_tags` / `target_source` 推导 source_family 过滤，
          多家族时使用 OR 组合。
    """
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
    """把 `source_tags` 翻译为 source_family 级别的 MetadataFilter 列表。

    优先级：`source_tags` 非空时按显式标签映射；否则回退到 `target_source`；
    最终多个家族用 `FilterOperator.IN` 合成单个过滤项。
    """
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
    """为工作区每个系列生成一份"内容指纹签名"，作为索引一致性的判据。"""
    signatures: SeriesSignatureMap = {}
    for series in workspace.list_series():
        signatures[series.id] = _build_series_signature(workspace, series.id)
    return signatures


def _build_series_signature(workspace: VideoLibraryReader, series_id: str) -> SeriesSignature:
    """为一个系列生成签名：把每条视频的状态 + 4 类制品哈希拼成有序元组。

    系列不存在时返回空元组，便于"系列已被删除"这种边界情况。
    """
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
    """生成旧版全工作区签名（`(series_ids, video_parts)`），用于兼容历史 signature 文件。"""
    signatures = _build_series_signatures(workspace)
    return tuple(sorted(signatures)), tuple(sorted(item for signature in signatures.values() for item in signature))


def _artifact_fingerprint(value: object) -> str:
    """把任意 Pydantic / dict 对象序列化为 SHA1，作为内容指纹。

    `None` 返回字面量 `"0"`（与缺失制品区分）；其他值用 `model_dump(mode="json")`
    序列化后排序编码，保证字段顺序无关。
    """
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
    """遍历工作区所有系列，把每条视频的制品汇总成待索引文档列表（用于全量重建）。"""
    documents: list[RetrievalDocument] = []
    for series in workspace.list_series():
        documents.extend(_build_documents_for_series(workspace, series_id=series.id))
    return documents


def _build_documents_for_series(
    workspace: VideoLibraryReader,
    *,
    series_id: str,
) -> list[RetrievalDocument]:
    """为单个系列下的所有视频构建检索文档；系列不存在时返回空列表。"""
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
    """为单个视频读取四类制品并交给 `_build_documents_for_assets` 合成文档。"""
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
    """把四类制品（总结/转写/笔记/知识卡）按"存在则加入"的原则拼成文档列表。"""
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
    """把内部 `RetrievalDocument` 转换为 LlamaIndex `Document`，并把 `doc_id` 作为主键。"""
    return [
        Document(
            id_=str(document.metadata["doc_id"]),
            text=document.text,
            metadata=document.metadata,
        )
        for document in documents
    ]


def _build_summary_documents(summary) -> list[RetrievalDocument]:
    """把视频总结拆成"全局总览 + 每章一条"的检索文档。

    全局文档包含一句话总结/核心问题/关键要点；每个章节单独成一条，便于按
    章节做精细化检索。
    """
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
    """把转写中每个 segment 转为一条 `transcript_chunk` 文档，metadata 含起止时间。"""
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
    """把每条笔记转成 `note` 文档，metadata 含 `note_id` 与 `note_source`。

    空标题或空内容的笔记会被跳过。
    """
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
    """把每张知识卡转成 `knowledge_card` 文档，metadata 含 `card_id` 与 `card_kind`。

    文本拼接顺序为 title → summary → details → keywords；空文本会被跳过。
    """
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
    """为 metadata 补齐 `COMMON_METADATA_DEFAULTS` 中的缺省键，并把 `None` 归一为空字符串。"""
    merged = dict(COMMON_METADATA_DEFAULTS)
    merged.update(metadata)
    for key in ("chapter_title", "note_id", "note_source", "card_id", "card_kind"):
        if merged.get(key) is None:
            merged[key] = ""
    return merged


def _reset_lancedb_table(db_uri: str, table_name: str) -> None:
    """删除指定 LanceDB 表；不存在时静默忽略（用于调试或重建前清空）。"""
    connection = lancedb.connect(db_uri)
    try:
        connection.drop_table(table_name)
    except Exception:
        # table 不存在时直接忽略，后续会重建
        pass


def _delete_rows(*, db_uri: str, table_name: str, where: str) -> None:
    """按 SQL 风格的 `where` 条件从 LanceDB 表中删除若干行（无则抛异常）。"""
    connection = lancedb.connect(db_uri)
    table = connection.open_table(table_name)
    table.delete(where)


def _optimize_lancedb_table(db_uri: str, table_name: str) -> None:
    """对 LanceDB 表执行合并清理，删除 10 分钟以上的旧版本（清理时机不可控）。"""
    connection = lancedb.connect(db_uri)
    table = connection.open_table(table_name)
    table.optimize(cleanup_older_than=LANCEDB_OPTIMIZE_CLEANUP_OLDER_THAN)


def _table_exists(db_uri: str, table_name: str) -> bool:
    """判断指定 LanceDB 表是否存在；连接或列举失败时保守返回 `False`。"""
    connection = lancedb.connect(db_uri)
    try:
        table_names = set(connection.table_names())
    except Exception:
        return False
    return table_name in table_names


def _escape_lance_string(value: str) -> str:
    """把字符串中的 `\\` 与 `'` 转义，供 SQL `where` 子串拼接使用。"""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _signature_file_path(db_uri: str, table_name: str) -> Path:
    """返回给定 (db_uri, table_name) 对应的 signature 文件路径。"""
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
    """读取 signature 文件并解析为 `SeriesSignatureMap`；兼容旧版全工作区签名格式。

    文件不存在或解析失败时返回 `None`，由调用方决定是否走全量重建。
    """
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
    """把旧版 `(series_ids, video_parts)` 签名转换为按系列分组的 `SeriesSignatureMap`。"""
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
    """对转写命中按 `context_window_seconds` 前后扩展，输出更完整的文本片段。

    若命中缺少起止时间或转写读取失败，则原样返回 `hit`；
    若窗口内没有任何分片，也保持原 hit 不变。
    """
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
    """把工具栏的 `ToolState` 序列化为简化的状态字典，供 LLM/前端消费。"""
    return {
        "id": tool.id,
        "title": tool.title,
        "available": tool.available,
        "generated": tool.generated,
        "status": tool.status,
    }
