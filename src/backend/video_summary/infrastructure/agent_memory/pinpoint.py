from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import cached_property

from backend.video_summary.library.ports import VideoLibraryReader


GET_VIDEO_TRANSCRIPT_TOOL_NAME = "get_video_transcript"
VIDEO_SEEK_TOOL_NAME = "video_seek"


class SemanticScorer:
    def score(self, *, query: str, texts: list[str]) -> list[float]:
        raise NotImplementedError


@dataclass(frozen=True)
class BGEReranker(SemanticScorer):
    model_name: str = "BAAI/bge-reranker-v2-m3"
    device: str = "cpu"

    @cached_property
    def _model(self):
        from sentence_transformers import CrossEncoder

        return CrossEncoder(self.model_name, device=_normalize_reranker_device(self.device))

    def score(self, *, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        raw_scores = self._model.predict(
            [(query, text) for text in texts],
            show_progress_bar=False,
        )
        return [float(_sigmoid(score)) for score in raw_scores]


class VideoGraphPinpointService:
    def __init__(self, *, workspace: VideoLibraryReader, semantic_scorer: SemanticScorer | None = None) -> None:
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
    compact = re.sub(r"\s+", "", text)
    return compact[:24] if len(compact) > 24 else compact


def _split_parallel_probe_part(part: str) -> list[str]:
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
    if value >= 0:
        exponent = math.exp(-value)
        return 1 / (1 + exponent)
    exponent = math.exp(value)
    return exponent / (1 + exponent)


def _normalize_reranker_device(device: str) -> str:
    normalized = device.strip().lower()
    if normalized in {"gpu", "cuda", "auto"}:
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    return "cpu"


def _append_pinpoint_trace(debug_trace: dict[str, object], entry: dict[str, object]) -> None:
    if not isinstance(debug_trace.get("pinpoint"), list):
        debug_trace["pinpoint"] = []
    debug_trace["pinpoint"].append(entry)
