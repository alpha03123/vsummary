"""AI 概括与下游制品共用的图片标记、画面上下文辅助函数。"""

from __future__ import annotations

from backend.video_summary.library.models import VideoSummaryDTO
from backend.video_summary.library.note_images import parse_note_image_markers


def _split_note_title(content: str, *, fallback: str) -> tuple[str, str]:
    """把模型输出的首行一级标题拆出来作为笔记标题。

    提示词要求正文第一行是 `# 标题`；拆出后从正文中移除，避免与笔记详情页
    自身的标题重复渲染。首行不是一级标题时标题回退到 `fallback`。

    Args:
        content: 模型返回的 Markdown 笔记。
        fallback: 没有可用标题时的兜底标题（通常是视频标题）。

    Returns:
        `(笔记标题, 去掉标题行后的正文)`。
    """
    stripped = content.lstrip("\n")
    first_line, _, rest = stripped.partition("\n")
    heading = first_line.strip()
    if heading.startswith("# "):
        title = heading[2:].strip().strip("#").strip()
        if title:
            return title, rest.lstrip("\n")
    return fallback, content


def constrain_ai_note_image_markers(
    content: str,
    *,
    summary: VideoSummaryDTO | None,
    duration_seconds: float,
    enabled: bool,
    max_images: int,
    min_gap_seconds: float,
) -> str:
    """过滤不满足自动配图约束的 AI 概括标记，手动笔记不走此函数。"""
    markers = parse_note_image_markers(content)
    if not enabled:
        return _filter_markers(content, set())
    accepted: set[tuple[int, int]] = set()
    kept: set[tuple[int, int]] = set()
    for marker in markers:
        # 超时长标记仍保留在正文中，由前端呈现不可用占位；它不消耗图片配额。
        if marker.seconds > duration_seconds:
            kept.add((marker.start, marker.end))
            continue
        if len(accepted) >= max_images:
            continue
        chapter = _find_chapter(summary, marker.seconds)
        if chapter is None:
            # 章节间缝隙不是用户或模型的错误，保留该时刻并正常抽帧。
            accepted.add((marker.start, marker.end))
            continue
        start, end, overview_timestamps = chapter
        short_chapter = end - start < min_gap_seconds * 2
        if any(
            marker.seconds == timestamp if short_chapter else abs(marker.seconds - timestamp) < min_gap_seconds
            for timestamp in overview_timestamps
        ):
            continue
        accepted.add((marker.start, marker.end))
    return _filter_markers(content, accepted | kept)


def _filter_markers(content: str, accepted: set[tuple[int, int]]) -> str:
    """仅保留指定位置的合法标记；不合法标记本来就不会被解析或删除。"""
    markers = parse_note_image_markers(content)
    if not markers:
        return content
    parts: list[str] = []
    previous = 0
    for marker in markers:
        parts.append(content[previous:marker.start])
        if (marker.start, marker.end) in accepted:
            parts.append(marker.raw)
        previous = marker.end
    parts.append(content[previous:])
    return "".join(parts)


def _overview_timestamps_by_chapter(summary: VideoSummaryDTO | None) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    if summary is None:
        return result
    chapters = summary.summary.get("chapters")
    if not isinstance(chapters, list):
        return result
    for chapter in chapters:
        if isinstance(chapter, dict) and isinstance(chapter.get("id"), str) and isinstance(chapter.get("image_timestamp_seconds"), (int, float)):
            result.setdefault(chapter["id"], []).append(float(chapter["image_timestamp_seconds"]))
    return result


def _find_chapter(summary: VideoSummaryDTO | None, seconds: float):
    if summary is None:
        return None
    chapters = summary.summary.get("chapters")
    if not isinstance(chapters, list):
        return None
    timestamps_by_chapter = _overview_timestamps_by_chapter(summary)
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        start = chapter.get("start_seconds")
        end = chapter.get("end_seconds")
        chapter_id = chapter.get("id")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and isinstance(chapter_id, str) and start <= seconds <= end:
            return float(start), float(end), timestamps_by_chapter.get(chapter_id, [])
    return None
