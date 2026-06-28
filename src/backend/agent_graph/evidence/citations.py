"""把 LangGraph 节点产出的 `evidence_items` 翻译为前端可渲染的 citation 列表。

`build_citations_from_graph_result` 是 series / video scope 共用的
citation 构造入口：读取图节点结果里的 `evidence_items`（或旧字段
`retrieval_results`），按 `source_type` / `depth` 分发到不同分支，
最终生成 `CitationReference` 列表，供前端按 inline / footnote / 章节
卡片等样式渲染。
"""

from __future__ import annotations

from backend.agent.schemas.action_plan import CitationReference, CitationSlot, CitationSlotCandidate


def build_citations_from_graph_result(result: dict[str, object]) -> list[CitationReference]:
    """从 LangGraph 节点结果中抽取并构造 citation 列表。

    处理流程：
    1. 优先取 `evidence_items`；缺失时回退到旧字段 `retrieval_results`；
    2. 必要时为每条证据补 `source_number`，与 LLM 输出的 `[1]`/`[2]`
       引用对齐；
    3. 若 `result["used_evidence_ids"]` 存在，则按它过滤出"实际被回答引用"
       的子集（与 `resolve_inline_citations` 配合做双向校验）；
    4. 按 `depth` 与 `source_type` 分发：summary / video_graph 走聚合
       展开；web_search 走 URL citation；其它按 summary / transcript
       生成单/双 slot 的 citation。

    Args:
        result: LangGraph 节点产生的状态字典，应至少包含
            `evidence_items` 或 `retrieval_results`；可选包含
            `used_evidence_ids` 用于过滤。

    Returns:
        前端可渲染的 `CitationReference` 列表。
    """
    retrieval_results = result.get("evidence_items", result.get("retrieval_results", []))
    if not isinstance(retrieval_results, list):
        return []
    retrieval_results = _with_source_numbers(retrieval_results)
    used_evidence_ids = _resolve_used_evidence_ids(result)
    used_citation_ids = _resolve_used_citation_ids(result)
    if used_evidence_ids is not None:
        retrieval_results = [
            item for item in retrieval_results
            if isinstance(item, dict) and _evidence_id(item) in used_evidence_ids
        ]

    citations: list[CitationReference] = []
    next_id = 1
    for item in retrieval_results:
        if not isinstance(item, dict):
            continue
        citation_id = _citation_id(item, next_id)
        depth = str(item.get("depth", "")).strip()
        if depth == "summary":
            next_id = _append_summary_items(citations, item.get("items", []), next_id)
            continue
        if depth == "video_graph":
            next_id = _append_video_graph_items(citations, item.get("items", []), next_id)
            continue
        source_type = str(item.get("source_type", "")).strip()
        if source_type == "web_search":
            next_id = _append_web_search_item(citations, item, next_id)
            continue

        video_id = str(item.get("video_id", "")).strip()
        title = str(item.get("title", "")).strip() or video_id
        if not source_type or not video_id:
            continue

        if source_type in {"summary", "summary_global", "summary_chapter", "series_synopsis"}:
            citations.append(
                CitationReference(
                    id=citation_id,
                    label=title,
                    source_type="summary",
                    search_scope="summary",
                    slots=[
                        CitationSlot(
                            slot=1,
                            target_type="summary",
                            video_id=video_id,
                            video_title=title,
                            chapter_id=_as_str(item.get("chapter_id")),
                            text=_as_str(item.get("snippet")) or _as_str(item.get("text")) or "summary evidence",
                        )
                    ],
                )
            )
            next_id += 1
            continue

        if source_type in {"transcript_chunk", "transcript_full"}:
            segment_citations = _transcript_segment_citations(
                item=item,
                citation_id=citation_id,
                title=title,
                used_citation_ids=used_citation_ids,
            )
            if segment_citations:
                citations.extend(segment_citations)
                next_id += 1
                continue
            if used_citation_ids is not None:
                next_id += 1
                continue
            slot_candidates = _to_slot_candidates(item.get("matches"))
            best_match = item.get("best_match")
            if isinstance(best_match, dict):
                best_start = _as_float(best_match.get("start_seconds"))
                best_end = _as_float(best_match.get("end_seconds"))
                best_text = _as_str(best_match.get("text"))
            else:
                best_start = _as_float(item.get("start_seconds"))
                best_end = _as_float(item.get("end_seconds"))
                best_text = _as_str(item.get("snippet")) or _as_str(item.get("text"))
            citations.append(
                CitationReference(
                    id=citation_id,
                    label=_as_str(item.get("slot_label")) or _as_str(item.get("label")) or title,
                    source_type="transcript",
                    search_scope="transcript",
                    slots=[
                        CitationSlot(
                            slot=1,
                            target_type="video",
                            video_id=video_id,
                            video_title=title,
                            start_seconds=best_start,
                            end_seconds=best_end,
                        ),
                        CitationSlot(
                            slot=2,
                            target_type="transcript",
                            video_id=video_id,
                            video_title=title,
                            start_seconds=best_start,
                            end_seconds=best_end,
                            text=best_text,
                            candidates=slot_candidates,
                        ),
                    ],
                )
            )
            next_id += 1

    return citations


def _with_source_numbers(items: list[object]) -> list[object]:
    """为证据列表补 `source_number`，保留已经显式编号的项。

    Args:
        items: 任意形态的证据项列表。

    Returns:
        每项均为字典且带 `source_number`（从 1 开始）的列表；非字典或
        已有合法 `source_number` 的项原样保留。
    """
    numbered_items: list[object] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            numbered_items.append(item)
            continue
        if isinstance(item.get("source_number"), int):
            numbered_items.append(item)
            continue
        numbered_items.append({**item, "source_number": index})
    return numbered_items


def _resolve_used_evidence_ids(result: dict[str, object]) -> set[str] | None:
    """从结果中提取"回答实际引用"的 evidence_id 集合。

    Args:
        result: LangGraph 节点状态字典，可能含 `used_evidence_ids` 字段。

    Returns:
        去重后的 evidence_id 集合；若字段缺失则为 `None`（表示不过滤）；
        若字段存在但不是数组则抛 `ValueError`。
    """
    raw_ids = result.get("used_evidence_ids")
    if raw_ids is None:
        return None
    if not isinstance(raw_ids, list):
        raise ValueError("used_evidence_ids 必须是数组。")
    used_ids = {
        item.strip()
        for item in raw_ids
        if isinstance(item, str) and item.strip()
    }
    return used_ids


def _resolve_used_citation_ids(result: dict[str, object]) -> set[str] | None:
    """从结果中提取回答实际引用过的 citation id 集合。"""
    raw_ids = result.get("used_citation_ids")
    if raw_ids is None:
        return None
    if not isinstance(raw_ids, list):
        raise ValueError("used_citation_ids 必须是数组。")
    used_ids = {
        item.strip()
        for item in raw_ids
        if isinstance(item, str) and item.strip()
    }
    return used_ids


def _evidence_id(item: dict[str, object]) -> str | None:
    """读取证据项的 `evidence_id` 字段（缺失或空白时为 `None`）。

    Args:
        item: 证据项字典。

    Returns:
        非空 `evidence_id` 字符串；为 `None` 时表示该证据不可被引用过滤。
    """
    value = item.get("evidence_id")
    if not isinstance(value, str):
        return None
    evidence_id = value.strip()
    return evidence_id or None


def _citation_id(item: dict[str, object], fallback_id: int) -> str:
    """为 citation 选取稳定 ID：优先使用上游 `source_number`，否则用回退编号。

    Args:
        item: 证据项字典。
        fallback_id: 上游未带 `source_number` 时的回退编号。

    Returns:
        可用作 citation ID 的字符串。
    """
    source_number = item.get("source_number")
    if isinstance(source_number, int) and source_number > 0:
        return str(source_number)
    return str(fallback_id)


def _append_web_search_item(citations: list[CitationReference], item: dict[str, object], next_id: int) -> int:
    """追加一条 web_search 类型的 citation（无 URL 时跳过）。

    Args:
        citations: 累积输出的 citation 列表（就地修改）。
        item: web_search 证据项。
        next_id: 当前可用的 citation ID 起点。

    Returns:
        追加后下一条可用的 `next_id`。
    """
    url = _as_str(item.get("url"))
    if not url:
        return next_id
    title = _as_str(item.get("title")) or url
    citations.append(
        CitationReference(
            id=str(next_id),
            label=title,
            source_type="web",
            search_scope="web",
            slots=[
                CitationSlot(
                    slot=1,
                    target_type="web",
                    text=_as_str(item.get("snippet")) or _as_str(item.get("text")),
                    url=url,
                )
            ],
        )
    )
    return next_id + 1


def _append_summary_items(citations: list[CitationReference], items: object, next_id: int) -> int:
    """展开 `depth == "summary"` 的聚合证据，为每个子项追加 summary citation。

    Args:
        citations: 累积输出的 citation 列表（就地修改）。
        items: 聚合证据的 `items` 字段，应为字典列表。
        next_id: 当前可用的 citation ID 起点。

    Returns:
        追加后下一条可用的 `next_id`。
    """
    if not isinstance(items, list):
        return next_id
    for item in items:
        if not isinstance(item, dict):
            continue
        video_id = str(item.get("video_id", "")).strip()
        title = str(item.get("title", "")).strip() or video_id
        if not video_id:
            continue
        source_type = str(item.get("source_type", "")).strip() or "summary_global"
        citations.append(
            CitationReference(
                id=str(next_id),
                label=title,
                source_type=source_type,
                search_scope="summary",
                slots=[
                    CitationSlot(
                        slot=1,
                        target_type="summary",
                        video_id=video_id,
                        video_title=title,
                        chapter_id=_as_str(item.get("chapter_id")),
                        text=_as_str(item.get("snippet")) or _as_str(item.get("text")) or "summary evidence",
                    )
                ],
            )
        )
        next_id += 1
    return next_id


def _append_video_graph_items(citations: list[CitationReference], items: object, next_id: int) -> int:
    """展开 `depth == "video_graph"` 的图证据，仅保留 `transcript_chunk` 子项。

    Args:
        citations: 累积输出的 citation 列表（就地修改）。
        items: 图证据的 `items` 字段，应为字典列表。
        next_id: 当前可用的 citation ID 起点。

    Returns:
        追加后下一条可用的 `next_id`。
    """
    if not isinstance(items, list):
        return next_id
    for item in items:
        if not isinstance(item, dict):
            continue
        source_type = str(item.get("source_type", "")).strip() or "transcript_chunk"
        if source_type != "transcript_chunk":
            continue
        video_id = str(item.get("video_id", "")).strip()
        title = str(item.get("title", "")).strip() or video_id
        if not video_id:
            continue
        slot_candidates = _to_slot_candidates(item.get("matches"))
        best_match = item.get("best_match")
        if isinstance(best_match, dict):
            best_start = _as_float(best_match.get("start_seconds"))
            best_end = _as_float(best_match.get("end_seconds"))
            best_text = _as_str(best_match.get("text"))
        else:
            best_start = _as_float(item.get("start_seconds"))
            best_end = _as_float(item.get("end_seconds"))
            best_text = _as_str(item.get("snippet")) or _as_str(item.get("text"))
        citations.append(
            CitationReference(
                id=str(next_id),
                label=_as_str(item.get("slot_label")) or _as_str(item.get("label")) or title,
                source_type="transcript",
                search_scope="transcript",
                slots=[
                    CitationSlot(
                        slot=1,
                        target_type="video",
                        video_id=video_id,
                        video_title=title,
                        start_seconds=best_start,
                        end_seconds=best_end,
                    ),
                    CitationSlot(
                        slot=2,
                        target_type="transcript",
                        video_id=video_id,
                        video_title=title,
                        start_seconds=best_start,
                        end_seconds=best_end,
                        text=best_text,
                        candidates=slot_candidates,
                    ),
                ],
            )
        )
        next_id += 1
    return next_id


def _transcript_segment_citations(
    *,
    item: dict[str, object],
    citation_id: str,
    title: str,
    used_citation_ids: set[str] | None,
) -> list[CitationReference]:
    """把 transcript evidence 的 `segments` 展开为 `[N.M]` citation。"""
    raw_segments = item.get("segments")
    if not isinstance(raw_segments, list):
        return []
    citations: list[CitationReference] = []
    for index, segment in enumerate(raw_segments, start=1):
        if not isinstance(segment, dict):
            continue
        anchor_id = _as_str(segment.get("anchor_id")) or f"{citation_id}.{index}"
        if used_citation_ids is not None and anchor_id not in used_citation_ids:
            continue
        start_seconds = _as_float(segment.get("start_seconds"))
        if start_seconds is None:
            continue
        end_seconds = _as_float(segment.get("end_seconds"))
        text = _as_str(segment.get("text"))
        citations.append(
            CitationReference(
                id=anchor_id,
                label=_as_str(item.get("slot_label")) or _as_str(item.get("label")) or title,
                source_type="transcript",
                search_scope="transcript",
                slots=[
                    CitationSlot(
                        slot=1,
                        target_type="video",
                        video_id=str(item.get("video_id", "")).strip(),
                        video_title=title,
                        start_seconds=start_seconds,
                        end_seconds=end_seconds,
                    ),
                    CitationSlot(
                        slot=2,
                        target_type="transcript",
                        video_id=str(item.get("video_id", "")).strip(),
                        video_title=title,
                        start_seconds=start_seconds,
                        end_seconds=end_seconds,
                        text=text,
                    ),
                ],
            )
        )
    return citations


def _to_slot_candidates(matches: object) -> list[CitationSlotCandidate]:
    """把 `matches` 字段转成 `CitationSlotCandidate` 列表（最多取前 3 个）。

    Args:
        matches: 任意形态的 matches 字段；非列表时返回空列表。

    Returns:
        长度 ≤ 3 的 `CitationSlotCandidate` 列表。
    """
    if not isinstance(matches, list):
        return []
    candidates: list[CitationSlotCandidate] = []
    for match in matches[:3]:
        if not isinstance(match, dict):
            continue
        candidates.append(
            CitationSlotCandidate(
                start_seconds=_as_float(match.get("start_seconds")),
                end_seconds=_as_float(match.get("end_seconds")),
                text=_as_str(match.get("text")),
            )
        )
    return candidates


def _as_float(value: object) -> float | None:
    """把任意值宽松转成 `float`，失败时为 `None`。

    Args:
        value: 任意形态的输入。

    Returns:
        `int` / `float` 时返回 `float(value)`，其它情况为 `None`。
    """
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_str(value: object) -> str | None:
    """把任意值宽松转成去空白字符串，空白字符串视为 `None`。

    Args:
        value: 任意形态的输入。

    Returns:
        非空字符串返回去空白后的字符串，否则为 `None`。
    """
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None
