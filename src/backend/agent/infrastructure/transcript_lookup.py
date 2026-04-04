from __future__ import annotations

import re
from dataclasses import dataclass

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentTranscriptLookup, TranscriptLookupMatch, TranscriptLookupResult
from backend.video_summary.library.ports import VideoWorkspace

_TOKEN_PATTERN = re.compile(r"[0-9a-zA-Z]+|[\u4e00-\u9fff]+")
_NON_WORD_PATTERN = re.compile(r"[\s\W_]+", re.UNICODE)


@dataclass(frozen=True)
class _SearchCandidate:
    source: str
    text: str
    start_seconds: float
    end_seconds: float
    chapter_title: str | None


class WorkspaceTranscriptLookup(AgentTranscriptLookup):
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def lookup(self, context: AgentContext, query: str) -> TranscriptLookupResult:
        normalized_query = query.strip()
        if context.scope_type != "video" or not context.series_id or not context.video_id or not normalized_query:
            return TranscriptLookupResult(query=normalized_query, matches=[])

        summary = self._workspace.get_video_summary(context.series_id, context.video_id)
        if summary is None:
            return TranscriptLookupResult(query=normalized_query, matches=[])

        matches = self._search(summary.summary, normalized_query)
        return TranscriptLookupResult(query=normalized_query, matches=matches)

    def _search(self, summary: dict[str, object], query: str) -> list[TranscriptLookupMatch]:
        query_tokens = _extract_tokens(query)
        query_normalized = _normalize_text(query)
        query_bigrams = _build_bigrams(query_normalized)
        ranked_matches: list[TranscriptLookupMatch] = []

        for candidate in _build_candidates(summary):
            score = _score_candidate(candidate, query_normalized, query_tokens, query_bigrams)
            if score <= 0:
                continue
            ranked_matches.append(
                TranscriptLookupMatch(
                    source=candidate.source,
                    text=candidate.text,
                    start_seconds=candidate.start_seconds,
                    end_seconds=candidate.end_seconds,
                    chapter_title=candidate.chapter_title,
                    score=score,
                )
            )

        ranked_matches.sort(key=lambda item: (-item.score, item.start_seconds, item.end_seconds, item.source))
        return _deduplicate_matches(ranked_matches, limit=3)


def _build_candidates(summary: dict[str, object]) -> list[_SearchCandidate]:
    chapters = summary.get("chapters", [])
    if not isinstance(chapters, list):
        return []

    candidates: list[_SearchCandidate] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue

        chapter_title = _as_non_empty_string(chapter.get("title"))
        chapter_start = _as_seconds(chapter.get("start_seconds"))
        chapter_end = _as_seconds(chapter.get("end_seconds"))
        key_points = chapter.get("key_points", [])
        chapter_summary = _join_non_empty(
            chapter_title,
            _as_non_empty_string(chapter.get("summary")),
            *[point.strip() for point in key_points if isinstance(point, str) and point.strip()],
        )
        if chapter_summary and chapter_start is not None and chapter_end is not None:
            candidates.append(
                _SearchCandidate(
                    source="chapter",
                    text=chapter_summary,
                    start_seconds=chapter_start,
                    end_seconds=chapter_end,
                    chapter_title=chapter_title,
                )
            )

        for segment in chapter.get("transcript_segments", []):
            if not isinstance(segment, dict):
                continue
            segment_text = _as_non_empty_string(segment.get("text"))
            segment_start = _as_seconds(segment.get("start_seconds"))
            segment_end = _as_seconds(segment.get("end_seconds"))
            if not segment_text or segment_start is None or segment_end is None:
                continue
            candidates.append(
                _SearchCandidate(
                    source="transcript",
                    text=segment_text,
                    start_seconds=segment_start,
                    end_seconds=segment_end,
                    chapter_title=chapter_title,
                )
            )

    return candidates


def _score_candidate(candidate: _SearchCandidate, query_normalized: str, query_tokens: list[str], query_bigrams: set[str]) -> float:
    text_normalized = _normalize_text(candidate.text)
    if not text_normalized:
        return 0.0

    score = 10.0 if candidate.source == "transcript" else 0.0
    if query_normalized and query_normalized in text_normalized:
        score += 8.0

    for token in query_tokens:
        if token in text_normalized:
            score += 2.0 + min(len(token) * 0.15, 1.2)

    if query_bigrams:
        text_bigrams = _build_bigrams(text_normalized)
        overlap = len(query_bigrams & text_bigrams)
        if overlap > 0:
            score += (overlap / len(query_bigrams)) * 6.0

    return score


def _deduplicate_matches(matches: list[TranscriptLookupMatch], limit: int) -> list[TranscriptLookupMatch]:
    deduplicated: list[TranscriptLookupMatch] = []
    seen_keys: set[tuple[str, float, float]] = set()
    for match in matches:
        key = (match.source, match.start_seconds, match.end_seconds)
        if key in seen_keys:
            continue
        deduplicated.append(match)
        seen_keys.add(key)
        if len(deduplicated) >= limit:
            break
    return deduplicated


def _extract_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for token in _TOKEN_PATTERN.findall(value.lower()):
        cleaned = token.strip()
        if len(cleaned) < 2:
            continue
        tokens.append(cleaned)
    return tokens


def _normalize_text(value: str) -> str:
    return _NON_WORD_PATTERN.sub("", value.lower())


def _build_bigrams(value: str) -> set[str]:
    if len(value) < 2:
        return {value} if value else set()
    return {value[index : index + 2] for index in range(len(value) - 1)}


def _join_non_empty(*parts: str | None) -> str:
    return " ".join(part for part in parts if part)


def _as_non_empty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _as_seconds(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
