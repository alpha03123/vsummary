"""视频级精准定位（pinpoint）服务与语义打分抽象。

提供：
- `VideoGraphPinpointService`：把查询拆成多个 probe slot，并在转写中按
  词法+语义打分定位最佳匹配片段，同时产出可被 Agent 工具链消费的
  `video_seek` 结果；
- `SemanticScorer` / `BGEReranker`：语义打分抽象与基于 FastEmbed CrossEncoder
  的默认实现（支持 GPU/CPU 切换）。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import cached_property

from backend.video_summary.library.ports import VideoLibraryReader


GET_VIDEO_TRANSCRIPT_TOOL_NAME = "get_video_transcript"
VIDEO_SEEK_TOOL_NAME = "video_seek"


class SemanticScorer:
    """对一批候选文本相对同一查询给出相关性得分的抽象。

    实现方负责加载模型并返回 `0.0-1.0` 区间的分数；为 `None` 时上游将用 0
    填充，相当于退化为纯词法打分。
    """

    def score(self, *, query: str, texts: list[str]) -> list[float]:
        """对 `texts` 中每条文本相对 `query` 的相关性打分。

        Args:
            query: 用户查询字符串。
            texts: 候选文本列表（通常为转写分片）。

        Returns:
            与 `texts` 等长的分数列表，`texts` 为空时返回空列表。
        """
        raise NotImplementedError


@dataclass(frozen=True)
class BGEReranker(SemanticScorer):
    """基于 FastEmbed CrossEncoder 的 BGE 重排序打分器。

    默认使用 `BAAI/bge-reranker-base`，支持 GPU/CPU 切换；模型首次访问时
    懒加载，缓存在实例的 `_model` 字段（`cached_property`）。

    Attributes:
        model_name: 重排序模型名称。
        device: 设备标识（`cpu` / `gpu` / `cuda`），由 `_normalize_reranker_device` 归一化。
        cache_dir: FastEmbed 模型缓存目录；为 `None` 时走默认缓存路径。
    """

    model_name: str = "BAAI/bge-reranker-base"
    device: str = "cpu"
    cache_dir: str | None = None

    @cached_property
    def _model(self):
        """懒加载 FastEmbed CrossEncoder 实例。

        根据 `device` 决定使用 CUDAExecutionProvider 还是 CPUExecutionProvider；
        模型仅在首次访问时构建。
        """
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        kwargs: dict[str, object] = {"model_name": self.model_name}
        if self.cache_dir is not None:
            kwargs["cache_dir"] = self.cache_dir
        if _normalize_reranker_device(self.device) == "gpu":
            kwargs["providers"] = ["CUDAExecutionProvider"]
            kwargs["cuda"] = True
        else:
            kwargs["providers"] = ["CPUExecutionProvider"]
        return TextCrossEncoder(**kwargs)

    def score(self, *, query: str, texts: list[str]) -> list[float]:
        """对候选文本跑重排序并把原始分数映射到 0-1 区间（sigmoid）。

        Args:
            query: 用户查询字符串。
            texts: 候选文本列表。

        Returns:
            与 `texts` 等长的 0-1 分数列表；`texts` 为空时直接返回 `[]`。
        """
        if not texts:
            return []
        raw_scores = list(self._model.rerank(query, texts))
        return [float(_sigmoid(score)) for score in raw_scores]


class VideoGraphPinpointService:
    """在视频转写中做"精准定位"的检索服务。

    业务场景：Agent 在 video scope 下被问到"哪一节讲了 X"时，需要把多个
    sub-query 在转写片段里逐个定位并挑出最佳匹配，输出既能被前端
    `video_seek` 使用、也能驱动后续证据合成的结构化结果。
    """

    def __init__(self, *, workspace: VideoLibraryReader, semantic_scorer: SemanticScorer | None = None) -> None:
        """注入工作区读取端口与可选的语义打分器。

        Args:
            workspace: 用于按 (series_id, video_id) 取转写制品。
            semantic_scorer: 语义打分实现；为 `None` 时退化为纯词法打分。
        """
        self._workspace = workspace
        self._semantic_scorer = semantic_scorer

    def locate(
        self,
        *,
        series_id: str,
        video_id: str,
        query: str,
        debug_trace: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        """对查询在指定视频的转写中执行多 slot 精准定位。

        处理流程：
            1. 取视频转写；缺失时返回 `transcript_missing=True` 的兜底结果；
            2. 把 query 拆成多个 probe slot（按编号、分号或并列连接词）；
            3. 对每个 slot 在转写分片上做词法+语义打分并挑最佳匹配；
            4. 把全部 slot 的最佳匹配按时间戳排序后输出，并合成
               `get_video_transcript` 与 `video_seek` 工具调用结果。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            query: 用户查询字符串。
            debug_trace: 可选的调试 trace 字典；不为 `None` 时把每步结果追加到
                `pinpoint` 列表。

        Returns:
            一个二元组：
                - 第一个元素是定位结果字典（含 `best_match`、`matches`、`slots`
                  与 `transcript_missing` 等字段）；
                - 第二个元素是 Agent 工具调用结果列表（含
                  `get_video_transcript` 与若干 `video_seek`）。
        """
        transcript = self._workspace.get_video_transcript(series_id, video_id)
        if transcript is None:
            result = {
                "video_id": video_id,
                "query": query,
                "matches": [],
                "transcript_missing": True,
                "source_type": "transcript_chunk",
            }
            if debug_trace is not None:
                _append_pinpoint_trace(debug_trace, {"series_id": series_id, "video_id": video_id, "query": query, "transcript_missing": True})
            return result, []

        slots = _build_probe_slots(query)
        if not slots:
            slots = [{"slot_id": "primary", "label": "primary", "query": query}]

        slot_results: list[dict[str, object]] = []
        flattened_best_matches: list[dict[str, object]] = []
        for slot in slots:
            slot_query = str(slot.get("query", "")).strip() or query
            slot_label = str(slot.get("label", "")).strip() or slot_query
            slot_terms = extract_query_terms(slot_query)
            semantic_scores = self._semantic_scorer.score(
                query=slot_query,
                texts=[segment.text for segment in transcript.segments],
            ) if self._semantic_scorer is not None else [0.0] * len(transcript.segments)
            matches: list[dict[str, object]] = []
            for index, segment in enumerate(transcript.segments):
                searchable_text = segment.text.lower()
                matched_terms = [term for term in slot_terms if term in searchable_text]
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
                    }
                )
            matches.sort(key=lambda item: (-float(item["score"]), float(item["start_seconds"])))
            top_matches = matches[:VIDEO_GRAPH_SLOT_TOP_K] if matches else []
            best_match = _select_slot_best_match(matches)
            slot_results.append(
                {
                    "slot_id": str(slot.get("slot_id", "")).strip() or slot_label,
                    "label": slot_label,
                    "query": slot_query,
                    "terms": slot_terms,
                    "matches": top_matches,
                    "best_match": best_match,
                }
            )
            if best_match is not None:
                flattened_best_matches.append({**best_match, "slot_label": slot_label, "slot_query": slot_query})

        flattened_best_matches.sort(key=lambda item: float(item["start_seconds"]))
        best_match = flattened_best_matches[0] if flattened_best_matches else None
        result = {
            "video_id": transcript.video_id,
            "title": transcript.title,
            "query": query,
            "matches": flattened_best_matches,
            "slots": slot_results,
            "best_match": best_match,
            "transcript_missing": False,
            "source_type": "transcript_chunk",
        }
        tool_results = [
            {
                "tool_name": GET_VIDEO_TRANSCRIPT_TOOL_NAME,
                "status": "ok",
                "payload": {
                    "series_id": transcript.series_id,
                    "video_id": transcript.video_id,
                    "title": transcript.title,
                    "generated": True,
                    "match_count": len(flattened_best_matches),
                },
            }
        ]
        for match in flattened_best_matches:
            tool_results.append(
                {
                    "tool_name": VIDEO_SEEK_TOOL_NAME,
                    "status": "ok",
                    "payload": {
                        "series_id": transcript.series_id,
                        "video_id": transcript.video_id,
                        "seek_seconds": match["start_seconds"],
                        "match_end_seconds": match["end_seconds"],
                        "matched_text": match["text"],
                        "query": match["slot_query"],
                        "slot_label": match["slot_label"],
                    },
                }
            )
        if debug_trace is not None:
            _append_pinpoint_trace(
                debug_trace,
                {
                    "series_id": transcript.series_id,
                    "video_id": transcript.video_id,
                    "query": query,
                    "slots": slot_results,
                    "best_match": best_match,
                },
            )
        return result, tool_results


def extract_query_terms(query: str) -> list[str]:
    """从查询字符串抽取用于词法匹配的检索词列表。

    处理流程：
        1. 归一化小写；
        2. 用正则抽取英文/数字 token；
        3. 优先用 `jieba.cut_for_search` 切分中文，依赖缺失时回退到
           `[\u4e00-\u9fff]{2,}` 字符级匹配；
        4. 过滤停用词、过短项、纯标点项；
        5. 按出现顺序去重。

    Args:
        query: 原始查询字符串。

    Returns:
        检索词列表（去重、过滤后）。
    """
    normalized = query.lower()
    stop_terms = {
        "这个系列",
        "哪一节",
        "哪几节",
        "老师",
        "一下",
        "一个",
        "可以",
        "里面",
        "当前",
        "告诉我",
        "帮我",
    }
    terms: list[str] = []
    raw_terms = re.findall(r"[a-z0-9\-\._]{2,}", normalized)
    terms.extend(raw_terms)
    try:
        import jieba

        terms.extend(
            token.strip().lower()
            for token in jieba.cut_for_search(normalized)
            if isinstance(token, str) and token.strip()
        )
    except Exception:
        terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}", normalized))
    filtered_terms: list[str] = []
    for term in terms:
        compact = term.strip()
        if len(compact) < 2 or compact in stop_terms:
            continue
        if re.fullmatch(r"[\W_]+", compact):
            continue
        filtered_terms.append(compact)
    return list(dict.fromkeys(filtered_terms))


def _build_probe_slots(query: str) -> list[dict[str, str]]:
    """把多子句查询拆解成多个 probe slot，供后续逐个精准定位。

    拆分策略：
        1. 若含编号前缀（如 "1）"、"（2）"），按编号切片；
        2. 否则按 `；`、`;`、换行切成粗粒度片段；
        3. 再把每个片段按 "以及/和/、" 拆成并列探针，并把剥离的"时间段/原话"
           等公共后缀回填，避免切割后语义丢失。

    Args:
        query: 原始查询字符串。

    Returns:
        `[{slot_id, label, query}, ...]` 形式的 slot 列表；若拆不出任何 slot，
        调用方应自行兜底为一个 `primary` slot。
    """
    normalized = query.replace("\r\n", "\n").strip()
    numbered_parts = [
        part.strip(" ；;。.") for part in re.split(r"(?:^|[；;。\n])\s*(?:\d+[）\).、]|\([0-9]+\))\s*", normalized) if part and part.strip(" ；;。.")
    ]
    if len(numbered_parts) > 1:
        return [{"slot_id": f"slot_{index}", "label": _summarize_slot_label(part), "query": part} for index, part in enumerate(numbered_parts, start=1)]
    coarse_parts = [part.strip(" ；;。.") for part in re.split(r"[；;\n]", normalized) if part.strip(" ；;。.")]
    expanded_parts: list[str] = []
    for part in coarse_parts:
        expanded_parts.extend(_split_parallel_probe_part(part))
    unique_parts: list[str] = []
    for part in expanded_parts:
        if part not in unique_parts:
            unique_parts.append(part)
    return [{"slot_id": f"slot_{index}", "label": _summarize_slot_label(part), "query": part} for index, part in enumerate(unique_parts, start=1)]


def _summarize_slot_label(text: str) -> str:
    """把 slot 文本压缩成不超过 24 个字符的展示标签。"""
    compact = re.sub(r"\s+", "", text)
    return compact[:24] if len(compact) > 24 else compact


def _split_parallel_probe_part(part: str) -> list[str]:
    """把并列子句（如"X 和 Y 的时间段"）切成多个独立 probe。

    先剥离公共后缀（"时间段/原话"等），再按顶层 "以及/和/、" 切分，
    切完后再把剥离的后缀回填到每个子句，避免"哪个时间段"语义丢失。
    """
    trimmed = part.strip(" ；;。,.，")
    if not trimmed:
        return []
    suffix = ""
    body = trimmed
    for candidate in ("的时间段", "时间段", "的时间点", "时间点", "的位置", "位置", "的原话", "原话"):
        if body.endswith(candidate):
            suffix = candidate
            body = body[: -len(candidate)].rstrip(" ，,")
            break
    pieces = _split_top_level(body, separators=("以及", "和", "、"))
    if len(pieces) <= 1:
        return [trimmed]
    rebuilt: list[str] = []
    for piece in pieces:
        candidate = piece.strip(" ；;。,.，")
        if not candidate:
            continue
        if suffix and not candidate.endswith(suffix):
            candidate = f"{candidate}{suffix}"
        rebuilt.append(candidate)
    return rebuilt if len(rebuilt) > 1 else [trimmed]


def _split_top_level(text: str, *, separators: tuple[str, ...]) -> list[str]:
    """按分隔符切片，但忽略被成对括号包裹的部分（避免破坏"（A 和 B）"结构）。"""
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "([{（【":
            depth += 1
            buffer.append(char)
            index += 1
            continue
        if char in ")]}）】":
            depth = max(0, depth - 1)
            buffer.append(char)
            index += 1
            continue
        if depth == 0:
            matched = next((separator for separator in separators if text.startswith(separator, index)), "")
            if matched:
                part = "".join(buffer).strip()
                if part:
                    parts.append(part)
                buffer = []
                index += len(matched)
                continue
        buffer.append(char)
        index += 1
    tail = "".join(buffer).strip()
    if tail:
        parts.append(tail)
    return parts


def _lexical_score(matched_terms: list[str]) -> int:
    """按命中词的形态累计词法打分：数字词权重最高，英文/中文依次降低。"""
    score = 0
    for term in matched_terms:
        if any(char.isdigit() for char in term):
            score += 4
        elif re.fullmatch(r"[a-z0-9\\-\\._]{2,}", term):
            score += 3
        else:
            score += 2
    return score


def _select_slot_best_match(matches: list[dict[str, object]]) -> dict[str, object] | None:
    """从某 slot 的所有分片匹配中挑出"最佳匹配"。

    优先级：
        1. 优先选择词法打分 > 0 的命中（说明确实命中查询词）；
        2. 在词法打分相同的情况下按 `start_seconds` 升序，取最早的命中；
        3. 若所有分片词法打分都为 0，则退回到按综合得分排序后的第一条。
    """
    if not matches:
        return None
    lexical_matches = [
        item
        for item in matches
        if isinstance(item, dict) and isinstance(item.get("lexical_score"), int) and int(item.get("lexical_score", 0)) > 0
    ]
    if lexical_matches:
        max_lexical = max(int(item.get("lexical_score", 0)) for item in lexical_matches)
        strongest = [
            item
            for item in lexical_matches
            if int(item.get("lexical_score", 0)) == max_lexical
        ]
        strongest.sort(key=lambda item: float(item.get("start_seconds", 0.0)))
        return strongest[0]
    return matches[0]


VIDEO_GRAPH_SLOT_TOP_K = 3


def _sigmoid(value: float) -> float:
    """数值稳定的 sigmoid 实现（避免大负数下溢出）。"""
    if value >= 0:
        exponent = math.exp(-value)
        return 1 / (1 + exponent)
    exponent = math.exp(value)
    return exponent / (1 + exponent)


def _normalize_reranker_device(device: str) -> str:
    """把用户传入的设备字符串归一化为内部 `cpu` / `gpu` 标识。"""
    normalized = device.strip().lower()
    if normalized in {"gpu", "cuda"}:
        return "gpu"
    return "cpu"


def _append_pinpoint_trace(debug_trace: dict[str, object], entry: dict[str, object]) -> None:
    """把 pinpoint 步骤的诊断信息追加到 `debug_trace["pinpoint"]` 列表。"""
    if not isinstance(debug_trace.get("pinpoint"), list):
        debug_trace["pinpoint"] = []
    debug_trace["pinpoint"].append(entry)
