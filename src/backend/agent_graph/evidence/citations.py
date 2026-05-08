from __future__ import annotations

from backend.agent.schemas.action_plan import CitationReference, CitationSlot, CitationSlotCandidate


def build_citations_from_graph_result(result: dict[str, object]) -> list[CitationReference]:
    retrieval_results = result.get("evidence_items", result.get("retrieval_results", []))
    if not isinstance(retrieval_results, list):
        return []

    citations: list[CitationReference] = []
    next_id = 1
    for item in retrieval_results:
        if not isinstance(item, dict):
            continue
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
                    id=str(next_id),
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

        if source_type == "transcript_chunk":
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

    return citations


def _append_web_search_item(citations: list[CitationReference], item: dict[str, object], next_id: int) -> int:
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


def _to_slot_candidates(matches: object) -> list[CitationSlotCandidate]:
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
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_str(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None
