"""AI 概括与下游制品共用的图片标记、画面上下文辅助函数。"""

from __future__ import annotations

import math

from markdown_it import MarkdownIt

from backend.video_summary.library.note_images import parse_note_image_markers


AI_SUMMARY_SECTION_HEADING_LEVEL = 2
_MARKDOWN_PARSER = MarkdownIt("commonmark")


class AiSummaryImageCoverageError(ValueError):
    """AI 概括的有效图片数未达到按章节计算的最低目标。"""


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
    accepted_timestamps: list[float] = []
    kept: set[tuple[int, int]] = set()
    for marker in markers:
        # 超时长标记仍保留在正文中，由前端呈现不可用占位；它不消耗图片配额。
        if marker.seconds > duration_seconds:
            kept.add((marker.start, marker.end))
            continue
        if len(accepted) >= max_images:
            continue
        if any(abs(marker.seconds - timestamp) < min_gap_seconds for timestamp in accepted_timestamps):
            continue
        accepted.add((marker.start, marker.end))
        accepted_timestamps.append(marker.seconds)
    return _filter_markers(content, accepted | kept)


def validate_ai_summary_image_coverage(
    content: str,
    *,
    duration_seconds: float,
    enabled: bool,
    max_images: int,
) -> None:
    """确保自动配图覆盖足够多的 AI 概括章节。"""

    if not enabled:
        return
    chapter_count = count_ai_summary_sections(content)
    required_count = min(max_images, math.ceil(chapter_count * 0.9))
    if required_count == 0:
        return
    valid_timestamps = {
        round(marker.seconds, 3)
        for marker in parse_note_image_markers(content)
        if marker.seconds <= duration_seconds
    }
    actual_count = len(valid_timestamps)
    if actual_count < required_count:
        raise AiSummaryImageCoverageError(
            f"自动配图覆盖不足：概括有 {chapter_count} 个有效章节，"
            f"至少需要 {required_count} 张有效图片，当前只有 {actual_count} 张。"
        )


def count_ai_summary_sections(content: str) -> int:
    """统计 AI 概括的一级章节，与前端大纲中的二级标题语义一致。"""

    return sum(
        1
        for token in _MARKDOWN_PARSER.parse(content)
        if token.type == "heading_open" and token.tag == f"h{AI_SUMMARY_SECTION_HEADING_LEVEL}"
    )


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


    return None
