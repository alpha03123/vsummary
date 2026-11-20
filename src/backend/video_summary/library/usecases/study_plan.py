"""学习计划：把一个视频或一整个合集按每天的学习时长分成若干课。

分课由代码完成：每段章节的学习时间按观看时长乘 `STUDY_TIME_FACTOR` 估算（留出暂停、
记笔记的时间），按顺序装进每一课，超过一课容量的长章节按时间均分。模型只给切好的
每一课写标题、目标、重点和练习，所以天数和时间点都与视频一致。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

STUDY_TIME_FACTOR = 1.3
MIN_DAILY_MINUTES = 10
MAX_DAILY_MINUTES = 240
# 一课允许略超出每日时长，避免为几分钟的尾巴单独开一课；更长的章节按此上限均分。
_SESSION_OVERFLOW = 1.15
_SUMMARY_CHARS = 240
_KEY_POINTS = 4


@dataclass(frozen=True)
class _Piece:
    video_id: str
    video_title: str
    chapter_title: str
    start_seconds: float
    end_seconds: float
    summary: str
    key_points: tuple[str, ...]

    @property
    def study_minutes(self) -> float:
        return max(self.end_seconds - self.start_seconds, 0.0) / 60 * STUDY_TIME_FACTOR


class StudyPlanCopyGenerator(Protocol):
    async def arun(self, *, title: str, context: str, daily_minutes: int, sessions: list[dict]) -> Any: ...


def validate_daily_minutes(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_DAILY_MINUTES <= value <= MAX_DAILY_MINUTES:
        raise ValueError(f"daily_minutes must be an integer between {MIN_DAILY_MINUTES} and {MAX_DAILY_MINUTES}.")
    return value


def _chapter_pieces(video_id: str, video_title: str, summary: dict[str, Any], daily_minutes: int) -> list[_Piece]:
    pieces: list[_Piece] = []
    for chapter in summary.get("chapters") or []:
        start = float(chapter.get("start_seconds") or 0.0)
        end = max(float(chapter.get("end_seconds") or 0.0), start)
        title = str(chapter.get("title") or "").strip()
        text = " ".join(str(chapter.get("summary") or "").split())[:_SUMMARY_CHARS]
        points = tuple(str(point).strip() for point in (chapter.get("key_points") or [])[:_KEY_POINTS] if str(point).strip())
        parts = max(1, math.ceil((end - start) / 60 * STUDY_TIME_FACTOR / (daily_minutes * _SESSION_OVERFLOW)))
        step = (end - start) / parts
        for part in range(parts):
            label = f"{title}（{part + 1}/{parts}）" if parts > 1 else title
            pieces.append(_Piece(video_id, video_title, label, start + step * part,
                end if part == parts - 1 else start + step * (part + 1), text, points))
    return pieces


def pack_sessions(pieces: list[_Piece], daily_minutes: int) -> list[list[_Piece]]:
    """按顺序把片段分成若干课，让每课尽量接近每日时长（超出比不足罚得更重）。"""
    limit = daily_minutes * _SESSION_OVERFLOW
    prefix = [0.0]
    for piece in pieces:
        prefix.append(prefix[-1] + piece.study_minutes)
    best = [0.0] + [math.inf] * len(pieces)
    start_of = [0] * (len(pieces) + 1)
    for end in range(1, len(pieces) + 1):
        for start in range(end - 1, -1, -1):
            minutes = prefix[end] - prefix[start]
            if minutes > limit and end - start > 1:
                break
            gap = daily_minutes - minutes
            cost = best[start] + (gap * gap if gap >= 0 else 4 * gap * gap)
            if cost < best[end]:
                best[end], start_of[end] = cost, start
    sessions: list[list[_Piece]] = []
    end = len(pieces)
    while end > 0:
        sessions.append(pieces[start_of[end]:end])
        end = start_of[end]
    return sessions[::-1]


def _session_minutes(session: list[_Piece]) -> int:
    return max(1, round(sum(piece.study_minutes for piece in session)))


def _prompt_sessions(sessions: list[list[_Piece]], *, with_video_titles: bool) -> list[dict]:
    return [{
        "index": index,
        "study_minutes": _session_minutes(session),
        "segments": [{
            **({"video": piece.video_title} if with_video_titles else {}),
            "chapter": piece.chapter_title,
            "summary": piece.summary,
            "key_points": list(piece.key_points),
        } for piece in session],
    } for index, session in enumerate(sessions, start=1)]


def _clean_list(values: list[str], limit: int) -> list[str]:
    return [value.strip() for value in values if value and value.strip()][:limit]


def _build_plan(*, kind: str, title: str, daily_minutes: int, sessions: list[list[_Piece]], copy: Any) -> dict[str, Any]:
    written = {item.index: item for item in getattr(copy, "sessions", [])}
    plan_sessions = []
    for index, session in enumerate(sessions, start=1):
        item = written.get(index)
        plan_sessions.append({
            "index": index,
            "title": (item.title.strip() if item else "") or session[0].chapter_title,
            "goal": item.goal.strip() if item else "",
            "focus": _clean_list(item.focus, 4) if item else [],
            "practice": _clean_list(item.practice, 3) if item else [],
            "study_minutes": _session_minutes(session),
            "segments": [{
                "video_id": piece.video_id,
                "video_title": piece.video_title,
                "chapter_title": piece.chapter_title,
                "start_seconds": round(piece.start_seconds, 1),
                "end_seconds": round(piece.end_seconds, 1),
            } for piece in session],
        })
    return {
        "kind": kind,
        "title": title,
        "daily_minutes": daily_minutes,
        "total_minutes": sum(item["study_minutes"] for item in plan_sessions),
        "overview": copy.overview.strip(),
        "prerequisites": _clean_list(copy.prerequisites, 4),
        "sessions": plan_sessions,
    }


class GenerateStudyPlan:
    """读取已有总结，分课、请模型写每课内容，然后保存。"""

    def __init__(self, workspace, generator: StudyPlanCopyGenerator) -> None:
        self._workspace = workspace
        self._generator = generator

    async def for_video(self, series_id: str, video_id: str, *, daily_minutes: int) -> dict[str, Any] | None:
        summary = self._workspace.get_video_summary(series_id, video_id)
        if summary is None:
            return None
        pieces = _chapter_pieces(video_id, summary.title, summary.summary, daily_minutes)
        if not pieces:
            raise LookupError("The summary has no chapters; cannot build a study plan.")
        sessions = pack_sessions(pieces, daily_minutes)
        data = summary.summary
        context = "\n".join(line for line in (
            f"一句话概括：{data.get('one_sentence_summary', '')}" if data.get("one_sentence_summary") else "",
            f"核心问题：{data.get('core_problem', '')}" if data.get("core_problem") else "",
        ) if line)
        copy = await self._generator.arun(title=summary.title, context=context, daily_minutes=daily_minutes,
            sessions=_prompt_sessions(sessions, with_video_titles=False))
        plan = _build_plan(kind="video", title=summary.title, daily_minutes=daily_minutes, sessions=sessions, copy=copy)
        self._workspace.save_video_study_plan(series_id, video_id, plan=plan)
        return self._workspace.get_video_study_plan(series_id, video_id)

    async def for_series(self, series_id: str, *, daily_minutes: int) -> dict[str, Any] | None:
        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        if series is None:
            return None
        pieces: list[_Piece] = []
        outlines: list[str] = []
        for video in series.videos:
            summary = self._workspace.get_video_summary(series_id, video.id)
            if summary is None:
                continue
            pieces.extend(_chapter_pieces(video.id, summary.title, summary.summary, daily_minutes))
            outlines.append(f"- {summary.title}：{summary.summary.get('one_sentence_summary', '')}")
        if not pieces:
            return None
        sessions = pack_sessions(pieces, daily_minutes)
        context = "合集中已总结的视频（按顺序）：\n" + "\n".join(outlines)
        copy = await self._generator.arun(title=series.title, context=context, daily_minutes=daily_minutes,
            sessions=_prompt_sessions(sessions, with_video_titles=True))
        plan = _build_plan(kind="series", title=series.title, daily_minutes=daily_minutes, sessions=sessions, copy=copy)
        self._workspace.save_series_study_plan(series_id, plan=plan)
        return self._workspace.get_series_study_plan(series_id)
