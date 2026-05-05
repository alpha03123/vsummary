from __future__ import annotations

from backend.agent.schemas.tool_calls import ToolName
from backend.video_summary.infrastructure.agent_memory.pinpoint import SemanticScorer, _lexical_score, extract_query_terms


class VideoWorkflowExtractor:
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
                "tool_name": ToolName.GET_VIDEO_TRANSCRIPT.value,
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
                    "tool_name": ToolName.VIDEO_SEEK.value,
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
    compact = "".join(text.split())
    return compact[:24] if len(compact) > 24 else compact
