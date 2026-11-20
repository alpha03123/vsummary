"""学习计划：把一个视频或一整个合集按每天的学习时长分成若干课。

分工：模型决定学习顺序和每课包含哪些章节（这需要理解内容，比如先建表再查询），并写每课的
标题、目标、重点和练习；代码给章节编号、校验模型的分课，并计算全部时间点和时长，所以
时间点一定与视频一致。模型的分课不合格时退回代码分课：标题带编号就按编号排序，只在视频
边界分天，再请模型为切好的课写内容。

每课时长 = 观看时长 × `WATCH_FACTOR`（暂停、回看）+ 练习时间（模型按题目估计，限制在
`MIN_PRACTICE_MINUTES`–`MAX_PRACTICE_MINUTES`）。
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from uuid import uuid4
from typing import Any, Protocol

logger = logging.getLogger(__name__)

WATCH_FACTOR = 1.2
DEFAULT_PRACTICE_MINUTES = 10
MIN_PRACTICE_MINUTES = 5
MAX_PRACTICE_MINUTES = 20
MIN_DAILY_MINUTES = 10
MAX_DAILY_MINUTES = 240
# 一课允许略超出每日时长，避免为几分钟的尾巴单独开一课；更长的章节按此上限均分。
_SESSION_OVERFLOW = 1.15
# 模型排的课超过每日时长这么多倍（且不止一个章节）就算不合格。
_MODEL_SESSION_LIMIT = 1.5
_SUMMARY_CHARS = 240
_KEY_POINTS = 4
_LEADING_NUMBER = re.compile(r"^\D{0,4}?(\d+(?:[.\-_]\d+)*)")


@dataclass(frozen=True)
class _Piece:
    id: str
    video_id: str
    video_title: str
    order: int  # 在所属视频里的先后
    chapter_title: str
    start_seconds: float
    end_seconds: float
    summary: str
    key_points: tuple[str, ...]

    @property
    def watch_minutes(self) -> float:
        return max(self.end_seconds - self.start_seconds, 0.0) / 60 * WATCH_FACTOR


@dataclass
class _Video:
    id: str
    title: str
    outline: str
    pieces: list[_Piece] = field(default_factory=list)


class StudyPlanGenerator(Protocol):
    async def aplan(self, *, title: str, context: str, daily_minutes: int, videos: list[dict]) -> Any: ...

    async def acopy(self, *, title: str, context: str, daily_minutes: int, sessions: list[dict]) -> Any: ...


def validate_daily_minutes(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_DAILY_MINUTES <= value <= MAX_DAILY_MINUTES:
        raise ValueError(f"daily_minutes must be an integer between {MIN_DAILY_MINUTES} and {MAX_DAILY_MINUTES}.")
    return value


def _watch_capacity(daily_minutes: int) -> float:
    """每天留给看视频的分钟数：扣掉一课默认的练习时间，但至少留一半。"""
    return max(daily_minutes - DEFAULT_PRACTICE_MINUTES, daily_minutes / 2)


def _build_video(index: int, video_id: str, title: str, summary: dict[str, Any], daily_minutes: int) -> _Video:
    video = _Video(video_id, title, str(summary.get("one_sentence_summary") or "").strip())
    part_limit = _watch_capacity(daily_minutes) * _SESSION_OVERFLOW
    for chapter_no, chapter in enumerate(summary.get("chapters") or [], start=1):
        start = float(chapter.get("start_seconds") or 0.0)
        end = max(float(chapter.get("end_seconds") or 0.0), start)
        name = str(chapter.get("title") or "").strip()
        text = " ".join(str(chapter.get("summary") or "").split())[:_SUMMARY_CHARS]
        points = tuple(str(point).strip() for point in (chapter.get("key_points") or [])[:_KEY_POINTS] if str(point).strip())
        parts = max(1, math.ceil((end - start) / 60 * WATCH_FACTOR / part_limit))
        step = (end - start) / parts
        for part in range(parts):
            video.pieces.append(_Piece(
                id=f"v{index}c{chapter_no}" + (f"p{part + 1}" if parts > 1 else ""),
                video_id=video_id, video_title=title, order=len(video.pieces),
                chapter_title=f"{name}（{part + 1}/{parts}）" if parts > 1 else name,
                start_seconds=start + step * part,
                end_seconds=end if part == parts - 1 else start + step * (part + 1),
                summary=text, key_points=points))
    return video


def _number_key(title: str) -> tuple[int, ...] | None:
    match = _LEADING_NUMBER.match(title.strip())
    return tuple(int(part) for part in re.split(r"[.\-_]", match.group(1))) if match else None


def course_order(videos: list[_Video]) -> list[_Video]:
    """标题都以不重复的编号开头（4.1、P3、第 2 集）时按编号排，否则保持原顺序。"""
    keys = [_number_key(video.title) for video in videos]
    if len(videos) < 2 or any(key is None for key in keys) or len(set(keys)) != len(keys):
        return list(videos)
    return [video for _, video in sorted(zip(keys, videos), key=lambda pair: pair[0])]


def pack_sessions(videos: list[_Video], daily_minutes: int) -> list[list[_Piece]]:
    """代码分课：一个视频装得进一天就整段放进同一课，否则按章节拆；按顺序装，让每课观看时间
    尽量接近每天可用的时间（超出比不足罚得更重）。"""
    capacity = _watch_capacity(daily_minutes)
    limit = capacity * _SESSION_OVERFLOW
    blocks: list[list[_Piece]] = []
    for video in videos:
        if sum(piece.watch_minutes for piece in video.pieces) <= limit:
            blocks.append(video.pieces)
        else:
            blocks.extend([piece] for piece in video.pieces)
    blocks = [block for block in blocks if block]
    prefix = [0.0]
    for block in blocks:
        prefix.append(prefix[-1] + sum(piece.watch_minutes for piece in block))
    best = [0.0] + [math.inf] * len(blocks)
    start_of = [0] * (len(blocks) + 1)
    for end in range(1, len(blocks) + 1):
        for start in range(end - 1, -1, -1):
            minutes = prefix[end] - prefix[start]
            if minutes > limit and end - start > 1:
                break
            gap = capacity - minutes
            cost = best[start] + (gap * gap if gap >= 0 else 4 * gap * gap)
            if cost < best[end]:
                best[end], start_of[end] = cost, start
    sessions: list[list[_Piece]] = []
    end = len(blocks)
    while end > 0:
        sessions.append([piece for block in blocks[start_of[end]:end] for piece in block])
        end = start_of[end]
    return sessions[::-1]


def _practice_minutes(item: Any) -> int:
    value = getattr(item, "practice_minutes", 0) if item is not None else 0
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return DEFAULT_PRACTICE_MINUTES
    return min(max(value, MIN_PRACTICE_MINUTES), MAX_PRACTICE_MINUTES)


def _piece_prompt(piece: _Piece, *, with_id: bool) -> dict[str, Any]:
    return {
        **({"id": piece.id} if with_id else {}),
        "chapter": piece.chapter_title,
        "minutes": round(piece.watch_minutes, 1),
        "summary": piece.summary,
        "key_points": list(piece.key_points),
    }


def _plan_prompt_videos(videos: list[_Video]) -> list[dict]:
    return [{
        "video": video.title,
        **({"summary": video.outline} if video.outline else {}),
        "chapters": [_piece_prompt(piece, with_id=True) for piece in video.pieces],
    } for video in videos]


def _copy_prompt_sessions(sessions: list[list[_Piece]], *, with_video_titles: bool) -> list[dict]:
    return [{
        "index": index,
        "watch_minutes": max(1, round(sum(piece.watch_minutes for piece in session))),
        "segments": [{
            **({"video": piece.video_title} if with_video_titles else {}),
            **_piece_prompt(piece, with_id=False),
        } for piece in session],
    } for index, session in enumerate(sessions, start=1)]


def resolve_model_sessions(copy: Any, videos: list[_Video], daily_minutes: int) -> list[tuple[list[_Piece], Any]] | None:
    """核对模型的分课：每个章节恰好出现一次、同一视频内顺序不变、单课不过长。不合格返回 None。"""
    pieces = {piece.id: piece for video in videos for piece in video.pieces}
    resolved: list[tuple[list[_Piece], Any]] = []
    seen: set[str] = set()
    last_order: dict[str, int] = {}
    for item in getattr(copy, "sessions", None) or []:
        ids = [str(value).strip() for value in (getattr(item, "chapters", None) or [])]
        if not ids:
            return None
        session: list[_Piece] = []
        for piece_id in ids:
            piece = pieces.get(piece_id)
            if piece is None or piece_id in seen or piece.order <= last_order.get(piece.video_id, -1):
                return None
            seen.add(piece_id)
            last_order[piece.video_id] = piece.order
            session.append(piece)
        minutes = sum(piece.watch_minutes for piece in session) + _practice_minutes(item)
        if len(session) > 1 and minutes > daily_minutes * _MODEL_SESSION_LIMIT:
            return None
        resolved.append((session, item))
    return resolved if resolved and len(seen) == len(pieces) else None


def _clean_list(values: list[str] | None, limit: int) -> list[str]:
    return [value.strip() for value in (values or []) if value and value.strip()][:limit]


def _build_plan(*, kind: str, title: str, daily_minutes: int, videos: list[_Video],
                sessions: list[tuple[list[_Piece], Any]], copy: Any) -> dict[str, Any]:
    plan_sessions = []
    for index, (session, item) in enumerate(sessions, start=1):
        watch = sum(piece.watch_minutes for piece in session)
        practice = _practice_minutes(item)
        plan_sessions.append({
            "index": index,
            "title": (str(getattr(item, "title", "") or "").strip() if item else "") or session[0].chapter_title,
            "goal": str(getattr(item, "goal", "") or "").strip() if item else "",
            "focus": _clean_list(getattr(item, "focus", None), 4) if item else [],
            "practice": _clean_list(getattr(item, "practice", None), 3) if item else [],
            "watch_minutes": max(1, round(watch)),
            "practice_minutes": practice,
            "study_minutes": max(1, round(watch + practice)),
            "segments": [{
                "video_id": piece.video_id,
                "video_title": piece.video_title,
                "chapter_title": piece.chapter_title,
                "start_seconds": round(piece.start_seconds, 1),
                "end_seconds": round(piece.end_seconds, 1),
            } for piece in session],
        })
    video_seconds = sum(piece.end_seconds - piece.start_seconds for video in videos for piece in video.pieces)
    return {
        # 每次生成一个新编号；勾选进度时核对，避免把旧页面上的勾记到重新生成的计划上。
        "id": uuid4().hex,
        "kind": kind,
        "title": title,
        "daily_minutes": daily_minutes,
        "video_minutes": max(1, round(video_seconds / 60)),
        "total_minutes": sum(item["study_minutes"] for item in plan_sessions),
        "overview": str(getattr(copy, "overview", "") or "").strip(),
        "prerequisites": _clean_list(getattr(copy, "prerequisites", None), 4),
        "sessions": plan_sessions,
    }


class GenerateStudyPlan:
    """读取已有总结，请模型排课并写内容（不合格时代码排课），然后保存。"""

    def __init__(self, workspace, generator: StudyPlanGenerator) -> None:
        self._workspace = workspace
        self._generator = generator

    async def _plan(self, *, kind: str, title: str, context: str, daily_minutes: int, videos: list[_Video]) -> dict[str, Any]:
        videos = course_order([video for video in videos if video.pieces])
        copy = await self._generator.aplan(title=title, context=context, daily_minutes=daily_minutes,
            videos=_plan_prompt_videos(videos))
        sessions = resolve_model_sessions(copy, videos, daily_minutes)
        if sessions is None:
            logger.warning("Study plan: the model's lesson split failed validation; falling back to code packing.")
            packed = pack_sessions(videos, daily_minutes)
            copy = await self._generator.acopy(title=title, context=context, daily_minutes=daily_minutes,
                sessions=_copy_prompt_sessions(packed, with_video_titles=kind == "series"))
            written = {getattr(item, "index", None): item for item in getattr(copy, "sessions", None) or []}
            sessions = [(session, written.get(index)) for index, session in enumerate(packed, start=1)]
        return _build_plan(kind=kind, title=title, daily_minutes=daily_minutes, videos=videos, sessions=sessions, copy=copy)

    async def for_video(self, series_id: str, video_id: str, *, daily_minutes: int) -> dict[str, Any] | None:
        summary = self._workspace.get_video_summary(series_id, video_id)
        if summary is None:
            return None
        video = _build_video(1, video_id, summary.title, summary.summary, daily_minutes)
        if not video.pieces:
            raise LookupError("The summary has no chapters; cannot build a study plan.")
        data = summary.summary
        context = "\n".join(line for line in (
            f"核心问题：{data.get('core_problem', '')}" if data.get("core_problem") else "",
        ) if line)
        plan = await self._plan(kind="video", title=summary.title, context=context, daily_minutes=daily_minutes, videos=[video])
        self._workspace.save_video_study_plan(series_id, video_id, plan=plan)
        return self._workspace.get_video_study_plan(series_id, video_id)

    async def for_series(self, series_id: str, *, daily_minutes: int) -> dict[str, Any] | None:
        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        if series is None:
            return None
        videos: list[_Video] = []
        for video in series.videos:
            summary = self._workspace.get_video_summary(series_id, video.id)
            if summary is not None:
                videos.append(_build_video(len(videos) + 1, video.id, summary.title, summary.summary, daily_minutes))
        if not any(video.pieces for video in videos):
            return None
        plan = await self._plan(kind="series", title=series.title, context="", daily_minutes=daily_minutes, videos=videos)
        self._workspace.save_series_study_plan(series_id, plan=plan)
        return self._workspace.get_series_study_plan(series_id)
