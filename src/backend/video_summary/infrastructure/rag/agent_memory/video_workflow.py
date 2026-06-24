"""视频工作流多 aspect 抽取器（按"工作流式窗口"聚合证据）。

与 `pinpoint.py` 的"逐 slot 精准定位"不同，本模块把一个查询拆成多个 aspect，
各自在转写里找到最佳 anchor，再围绕 anchor 扩展成时间窗口并按间隙合并，
用于覆盖"按工作流讲解一段流程"这类多跳问题。
"""

from __future__ import annotations

from backend.video_summary.infrastructure.rag.agent_memory.pinpoint import SemanticScorer, _lexical_score, extract_query_terms


GET_VIDEO_TRANSCRIPT_TOOL_NAME = "get_video_transcript"
VIDEO_SEEK_TOOL_NAME = "video_seek"


class VideoWorkflowExtractor:
    """基于"工作流窗口"的视频证据抽取器。

    业务场景：当用户在 video scope 下问"按流程讲讲 X 是怎么做的"，单点
    pinpoint 不能覆盖整段流程；本类把查询拆成多个 aspect、各自定位 anchor，
    然后按 `window_before_seconds`/`window_after_seconds`/`merge_gap_seconds`
    合并为若干时间窗口，并按 anchor 数量从高到低排序输出。
    """

    def __init__(
        self,
        *,
        workspace,
        semantic_scorer: SemanticScorer | None = None,
        window_before_seconds: float = 120.0,
        window_after_seconds: float = 180.0,
        merge_gap_seconds: float = 30.0,
        max_anchor_count: int = 6,
    ) -> None:
        """注入工作区读取端口与窗口合并参数。

        Args:
            workspace: 用于按 (series_id, video_id) 取转写制品。
            semantic_scorer: 语义打分实现；为 `None` 时退化为纯词法打分。
            window_before_seconds: 每个 anchor 向前扩展的秒数。
            window_after_seconds: 每个 anchor 向后扩展的秒数。
            merge_gap_seconds: 窗口之间允许的最大间隙；小于该间隙会合并。
            max_anchor_count: 最终保留的最大 anchor 数量（去重后）。
        """
        self._workspace = workspace
        self._semantic_scorer = semantic_scorer
        self._window_before_seconds = window_before_seconds
        self._window_after_seconds = window_after_seconds
        self._merge_gap_seconds = merge_gap_seconds
        self._max_anchor_count = max_anchor_count

    def extract(
        self,
        *,
        series_id: str,
        video_id: str,
        query: str,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        """对查询在指定视频中执行"多 aspect → 多窗口"抽取。

        处理流程：
            1. 取视频转写；缺失时返回 `transcript_missing=True` 的兜底结果；
            2. 把查询拆成多个 aspect，按 aspect 各自定位最佳 anchor；
            3. 去重并截断 anchor，按窗口参数扩展+合并，生成 windows 列表；
            4. 输出窗口级 `video_seek` 工具结果。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            query: 用户查询字符串。

        Returns:
            一个二元组：
                - 第一个元素是抽取结果字典（含 `windows` / `best_window` /
                  `anchors` 与 `transcript_missing` 字段）；
                - 第二个元素是 Agent 工具调用结果列表（含
                  `get_video_transcript` 与若干 `video_seek`）。
        """
        transcript = self._workspace.get_video_transcript(series_id, video_id)
        if transcript is None:
            return (
                {
                    "video_id": video_id,
                    "query": query,
                    "windows": [],
                    "best_window": None,
                    "anchors": [],
                    "transcript_missing": True,
                    "source_type": "workflow_window",
                },
                [],
            )
        aspects = _build_workflow_aspects(query)
        anchors: list[dict[str, object]] = []
        for aspect in aspects:
            aspect_anchor = _select_anchor_for_aspect(
                transcript=transcript,
                query=aspect,
                semantic_scorer=self._semantic_scorer,
            )
            if aspect_anchor is not None:
                anchors.append(aspect_anchor)
        anchors.sort(key=lambda item: float(item["start_seconds"]))
        deduped_anchors = _dedupe_anchors(anchors)[: self._max_anchor_count]
        windows = _build_windows(
            transcript=transcript,
            anchors=deduped_anchors,
            window_before_seconds=self._window_before_seconds,
            window_after_seconds=self._window_after_seconds,
            merge_gap_seconds=self._merge_gap_seconds,
        )
        best_window = windows[0] if windows else None
        result = {
            "video_id": transcript.video_id,
            "title": transcript.title,
            "query": query,
            "anchors": deduped_anchors,
            "windows": windows,
            "best_window": best_window,
            "transcript_missing": False,
            "source_type": "workflow_window",
        }
        tool_results: list[dict[str, object]] = [
            {
                "tool_name": GET_VIDEO_TRANSCRIPT_TOOL_NAME,
                "status": "ok",
                "payload": {
                    "series_id": transcript.series_id,
                    "video_id": transcript.video_id,
                    "title": transcript.title,
                    "generated": True,
                    "match_count": len(deduped_anchors),
                },
            }
        ]
        for anchor in deduped_anchors:
            tool_results.append(
                {
                    "tool_name": VIDEO_SEEK_TOOL_NAME,
                    "status": "ok",
                    "payload": {
                        "series_id": transcript.series_id,
                        "video_id": transcript.video_id,
                        "seek_seconds": anchor["start_seconds"],
                        "match_end_seconds": anchor["end_seconds"],
                        "matched_text": anchor["text"],
                        "query": anchor["aspect_query"],
                        "slot_label": anchor["aspect_label"],
                    },
                }
            )
        return result, tool_results


def _build_workflow_aspects(query: str) -> list[str]:
    """把查询拆成多个 aspect，用于工作流窗口式证据抽取。

    拆解策略：
        1. 先按换行切成行；
        2. 每行再按 `。！？?!；;` 进一步切成子句；
        3. 去重保留顺序；若拆不出任何子句则兜底返回 `[query]`。

    Args:
        query: 原始查询字符串。

    Returns:
        aspect 字符串列表（去重）。
    """
    parts = [
        part.strip(" ，,；;。！？?!.")
        for part in query.replace("\r\n", "\n").split("\n")
        for part in __import__("re").split(r"[。！？?!；;]", part)
        if part.strip(" ，,；;。！？?!.")
    ]
    unique_parts: list[str] = []
    for part in parts:
        if part not in unique_parts:
            unique_parts.append(part)
    return unique_parts or [query.strip()]


def _select_anchor_for_aspect(*, transcript, query: str, semantic_scorer: SemanticScorer | None) -> dict[str, object] | None:
    """为单个 aspect 在转写中选一个最佳 anchor。

    选优策略与 `pinpoint.py` 中保持一致：词法打分 > 0 的命中优先，
    同分取最早出现的分片；没有任何词法命中时退回到综合得分最高的分片。
    """
    terms = extract_query_terms(query)
    if not terms:
        return None
    semantic_scores = (
        semantic_scorer.score(query=query, texts=[segment.text for segment in transcript.segments])
        if semantic_scorer is not None
        else [0.0] * len(transcript.segments)
    )
    matches: list[dict[str, object]] = []
    for index, segment in enumerate(transcript.segments):
        searchable_text = segment.text.lower()
        matched_terms = [term for term in terms if term in searchable_text]
        lexical_score = _lexical_score(matched_terms)
        semantic_score = semantic_scores[index] if index < len(semantic_scores) else 0.0
        final_score = lexical_score * 10 + semantic_score * 4
        matches.append(
            {
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "text": segment.text,
                "matched_terms": matched_terms,
                "lexical_score": lexical_score,
                "semantic_score": round(semantic_score, 4),
                "score": round(final_score, 4),
                "aspect_query": query,
                "aspect_label": _summarize_aspect_label(query),
            }
        )
    matches.sort(key=lambda item: (-float(item["score"]), float(item["start_seconds"])))
    lexical_matches = [item for item in matches if int(item.get("lexical_score", 0)) > 0]
    if lexical_matches:
        max_lexical = max(int(item.get("lexical_score", 0)) for item in lexical_matches)
        strongest = [item for item in lexical_matches if int(item.get("lexical_score", 0)) == max_lexical]
        strongest.sort(key=lambda item: float(item["start_seconds"]))
        return strongest[0]
    return matches[0] if matches else None


def _dedupe_anchors(anchors: list[dict[str, object]]) -> list[dict[str, object]]:
    """按 `(start_seconds, end_seconds, text)` 三元组对 anchor 去重，保持原顺序。"""
    deduped: list[dict[str, object]] = []
    seen: set[tuple[float, float, str]] = set()
    for anchor in anchors:
        key = (
            float(anchor.get("start_seconds", 0.0)),
            float(anchor.get("end_seconds", 0.0)),
            str(anchor.get("text", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(anchor)
    return deduped


def _build_windows(
    *,
    transcript,
    anchors: list[dict[str, object]],
    window_before_seconds: float,
    window_after_seconds: float,
    merge_gap_seconds: float,
) -> list[dict[str, object]]:
    """把 anchor 列表扩展为时间窗口并按间隙合并，最终按 anchor 数量排序输出。

    步骤：
        1. 给每个 anchor 套上前后窗口形成原始窗口；
        2. 按时间顺序遍历，若当前窗口起点 ≤ 上一窗口终点 + 间隙则合并；
        3. 用落在窗口内的转写分片拼成窗口文本；
        4. 按 `anchor_count` 降序、`start_seconds` 升序排序。

    Args:
        transcript: 视频转写（用于截取窗口文本）。
        anchors: 去重后的 anchor 列表。
        window_before_seconds: anchor 向前扩展的秒数。
        window_after_seconds: anchor 向后扩展的秒数。
        merge_gap_seconds: 窗口之间允许的最大间隙（秒）。

    Returns:
        渲染后的窗口字典列表（每个含 `start_seconds`/`end_seconds`/`text`/
        `anchor_count`/`anchors`）；anchors 为空时返回 `[]`。
    """
    if not anchors:
        return []
    raw_windows = [
        {
            "start_seconds": max(0.0, float(anchor["start_seconds"]) - window_before_seconds),
            "end_seconds": float(anchor["end_seconds"]) + window_after_seconds,
            "anchors": [anchor],
        }
        for anchor in anchors
    ]
    merged_windows: list[dict[str, object]] = []
    for window in raw_windows:
        if not merged_windows:
            merged_windows.append(window)
            continue
        last = merged_windows[-1]
        if float(window["start_seconds"]) <= float(last["end_seconds"]) + merge_gap_seconds:
            last["end_seconds"] = max(float(last["end_seconds"]), float(window["end_seconds"]))
            last["anchors"].extend(window["anchors"])
            continue
        merged_windows.append(window)
    rendered_windows: list[dict[str, object]] = []
    for window in merged_windows:
        segments = [
            segment
            for segment in transcript.segments
            if float(segment.start_seconds) >= float(window["start_seconds"]) and float(segment.end_seconds) <= float(window["end_seconds"])
        ]
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        rendered_windows.append(
            {
                "start_seconds": float(window["start_seconds"]),
                "end_seconds": float(window["end_seconds"]),
                "text": text,
                "anchor_count": len(window["anchors"]),
                "anchors": [
                    {
                        "start_seconds": anchor["start_seconds"],
                        "end_seconds": anchor["end_seconds"],
                        "text": anchor["text"],
                        "aspect_query": anchor["aspect_query"],
                        "aspect_label": anchor["aspect_label"],
                    }
                    for anchor in window["anchors"]
                ],
            }
        )
    rendered_windows.sort(key=lambda item: (-int(item["anchor_count"]), float(item["start_seconds"])))
    return rendered_windows


def _summarize_aspect_label(text: str) -> str:
    """把 aspect 文本压缩成不超过 24 个字符的展示标签（去除所有空白）。"""
    compact = "".join(text.split())
    return compact[:24] if len(compact) > 24 else compact
