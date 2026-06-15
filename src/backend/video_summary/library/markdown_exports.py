"""视频库制品的 Markdown 渲染器。

把转写稿、知识卡、笔记、混合总览等制品 dict 序列化为可直接下载/分享的
Markdown 文本；同时附带强类型校验，缺字段时抛出 `ValueError`。
"""

from __future__ import annotations

from typing import Any

from backend.video_summary.generation.prompts import format_timestamp


def render_transcript_markdown(payload: dict[str, Any]) -> str:
    """把转写制品渲染为带时间戳小节的 Markdown。

    Args:
        payload: 包含 `title`、`language`（可选）、`duration_seconds`（可选）、
            `segments` 的字典，每个 segment 至少含 `start_seconds`/`end_seconds`/`text`。

    Returns:
        以 `\\n` 结尾的 Markdown 字符串。

    Raises:
        ValueError: 必填字段缺失或类型不匹配时抛出，错误信息含字段路径。
    """
    title = _require_text(payload.get("title"), "title")
    segments = _require_list(payload.get("segments"), "segments")

    lines = [f"# {title} 转写稿", ""]
    language = payload.get("language")
    if isinstance(language, str) and language.strip():
        lines.append(f"- 语言：{language.strip()}")
    duration = payload.get("duration_seconds")
    if isinstance(duration, int | float):
        lines.append(f"- 时长：{format_timestamp(float(duration))}")
    if len(lines) > 2:
        lines.append("")

    lines.append("## 原文转写")
    lines.append("")
    for index, item in enumerate(segments):
        if not isinstance(item, dict):
            raise ValueError(f"segments[{index}] 必须是对象。")
        start = _require_number(item.get("start_seconds"), f"segments[{index}].start_seconds")
        end = _require_number(item.get("end_seconds"), f"segments[{index}].end_seconds")
        text = _require_text(item.get("text"), f"segments[{index}].text")
        lines.append(f"### {format_timestamp(start)} - {format_timestamp(end)}")
        lines.append(text)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_knowledge_cards_markdown(payload: dict[str, Any]) -> str:
    """把知识卡集合渲染为 Markdown。

    Args:
        payload: 包含 `title` 与 `cards` 列表的字典；每张卡需要
            `title`/`kind`/`summary`/`details`/`tags`/`keywords` 字段。

    Returns:
        以 `\\n` 结尾的 Markdown 字符串，每张卡作为独立的 `##` 段落。

    Raises:
        ValueError: 必填字段缺失或类型不匹配时抛出。
    """
    title = _require_text(payload.get("title"), "title")
    cards = _require_list(payload.get("cards"), "cards")

    lines = [f"# {title} 知识卡片", ""]
    for index, item in enumerate(cards):
        if not isinstance(item, dict):
            raise ValueError(f"cards[{index}] 必须是对象。")
        lines.extend(_render_knowledge_card(item, index))

    return "\n".join(lines).strip() + "\n"


def render_notes_markdown(title: str, payload: dict[str, Any]) -> str:
    """把笔记集合渲染为 Markdown。

    Args:
        title: 笔记所属视频标题，直接用作 H1。
        payload: 包含 `notes` 列表的字典；每条笔记需要
            `title`/`content`/`source`/`created_at`/`updated_at`。

    Returns:
        以 `\\n` 结尾的 Markdown 字符串，每条笔记作为独立的 `##` 段落。

    Raises:
        ValueError: 必填字段缺失或类型不匹配时抛出。
    """
    notes = _require_list(payload.get("notes"), "notes")
    lines = [f"# {_require_text(title, 'title')} 笔记", ""]
    for index, item in enumerate(notes):
        if not isinstance(item, dict):
            raise ValueError(f"notes[{index}] 必须是对象。")
        lines.extend(_render_note(item, index))
    return "\n".join(lines).strip() + "\n"


def render_mixed_overview_markdown(summary_payload: dict[str, Any], transcript_payload: dict[str, Any]) -> str:
    """把总结 + 转写合并渲染为「章节纪要」Markdown。

    用于在工作区导出「总览 + 章节要点 + 章节对应原文」合并稿。
    每个章节会附带一个 `<details>` 折叠区，列出该章节时间区间内的转写片段。

    Args:
        summary_payload: 总结制品 dict，含 `title`/`core_problem`（可选）/
            `key_takeaways`（可选）/`chapters` 列表。
        transcript_payload: 转写制品 dict，含 `segments` 列表。

    Returns:
        以 `\\n` 结尾的 Markdown 字符串。

    Raises:
        ValueError: 必填字段缺失或类型不匹配时抛出。
    """
    title = _require_text(summary_payload.get("title"), "title")
    chapters = _require_list(summary_payload.get("chapters"), "chapters")
    transcript_segments = _require_list(transcript_payload.get("segments"), "segments")

    lines = [f"# {title}", ""]
    core_problem = summary_payload.get("core_problem")
    if isinstance(core_problem, str) and core_problem.strip():
        lines.extend(["## Core Problem", "", core_problem.strip(), ""])

    key_takeaways = summary_payload.get("key_takeaways")
    if isinstance(key_takeaways, list) and key_takeaways:
        lines.extend(["## Key Takeaways", ""])
        for index, takeaway in enumerate(key_takeaways):
            lines.append(f"- {_require_text(takeaway, f'key_takeaways[{index}]')}")
        lines.append("")

    lines.extend(["## 章节纪要", ""])
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            raise ValueError(f"chapters[{index}] 必须是对象。")
        lines.extend(_render_mixed_chapter(chapter, index, transcript_segments))
    return "\n".join(lines).strip() + "\n"


def _render_knowledge_card(card: dict[str, Any], index: int) -> list[str]:
    """把单张知识卡渲染为 Markdown 行列表（不含首尾换行的纯行序列）。

    Args:
        card: 知识卡 dict。
        index: 卡在父列表中的下标，用于错误信息定位。

    Returns:
        多行字符串列表，由调用方负责 `\\n` 拼接。

    Raises:
        ValueError: 必填字段缺失或类型不匹配时抛出。
    """
    title = _require_text(card.get("title"), f"cards[{index}].title")
    kind = _require_text(card.get("kind"), f"cards[{index}].kind")
    summary = _require_text(card.get("summary"), f"cards[{index}].summary")
    details = _require_text(card.get("details"), f"cards[{index}].details")
    tags = _require_text_list(card.get("tags"), f"cards[{index}].tags")
    keywords = _require_text_list(card.get("keywords"), f"cards[{index}].keywords")

    lines = [f"## {title}", "", f"- 类型：{kind}"]
    if tags:
        lines.append(f"- 标签：{'、'.join(tags)}")
    if keywords:
        lines.append(f"- 关键词：{'、'.join(keywords)}")
    lines.extend(["", "### 摘要", summary, "", "### 详情", details, ""])
    return lines


def _render_note(note: dict[str, Any], index: int) -> list[str]:
    """把单条笔记渲染为 Markdown 行列表。

    Args:
        note: 笔记 dict。
        index: 笔记在父列表中的下标，用于错误信息定位。

    Returns:
        多行字符串列表，由调用方负责 `\\n` 拼接。

    Raises:
        ValueError: 必填字段缺失或类型不匹配时抛出。
    """
    title = _require_text(note.get("title"), f"notes[{index}].title")
    content = _require_text(note.get("content"), f"notes[{index}].content")
    source = _require_text(note.get("source"), f"notes[{index}].source")
    created_at = _require_text(note.get("created_at"), f"notes[{index}].created_at")
    updated_at = _require_text(note.get("updated_at"), f"notes[{index}].updated_at")
    return [
        f"## {title}",
        "",
        f"- 来源：{source}",
        f"- 创建时间：{created_at}",
        f"- 更新时间：{updated_at}",
        "",
        content,
        "",
    ]


def _render_mixed_chapter(chapter: dict[str, Any], index: int, transcript_segments: list[object]) -> list[str]:
    """把单章节渲染为 Markdown 行列表，含要点列表与可选的原文折叠区。

    原文折叠区只在「章节时间区间内能匹配到转写片段」时出现；
    匹配的判定使用片段起止时间与章节起止时间的区间相交，而非严格相等。

    Args:
        chapter: 章节 dict，含 `title`/`start_seconds`/`end_seconds`/`summary`/`key_points`。
        index: 章节在父列表中的下标，用于错误信息定位。
        transcript_segments: 完整转写片段列表（未限定范围）。

    Returns:
        多行字符串列表，由调用方负责 `\\n` 拼接。

    Raises:
        ValueError: 必填字段缺失或类型不匹配时抛出。
    """
    title = _require_text(chapter.get("title"), f"chapters[{index}].title")
    start = _require_number(chapter.get("start_seconds"), f"chapters[{index}].start_seconds")
    end = _require_number(chapter.get("end_seconds"), f"chapters[{index}].end_seconds")
    summary = _require_text(chapter.get("summary"), f"chapters[{index}].summary")
    key_points = _require_text_list(chapter.get("key_points"), f"chapters[{index}].key_points")
    chapter_segments = _segments_in_range(transcript_segments, start, end)

    lines = [
        f"### Chapter {index + 1}",
        "",
        f"#### {title}",
        "",
        f"{format_timestamp(start)} - {format_timestamp(end)}",
        "",
        summary,
        "",
    ]
    for point in key_points:
        lines.append(f"- {point}")
    if key_points:
        lines.append("")
    if chapter_segments:
        lines.extend(
            [
                "<details>",
                "<summary>查看本章原文</summary>",
                "",
                f"{len(chapter_segments)} 段转写",
                "",
            ]
        )
        for segment in chapter_segments:
            lines.append(
                f"- {format_timestamp(segment['start_seconds'])} - "
                f"{format_timestamp(segment['end_seconds'])} {segment['text']}"
            )
        lines.extend(["", "</details>", ""])
    return lines


def _segments_in_range(segments: list[object], start: float, end: float) -> list[dict[str, Any]]:
    """筛选与给定时间区间有交集的转写片段。

    只要片段与 `[start, end]` 有任意重叠即视为「在范围内」；
    返回的字典仅保留 `start_seconds`/`end_seconds`/`text` 三个字段。

    Args:
        segments: 待筛选的转写片段列表。
        start: 区间起（秒，含）。
        end: 区间止（秒，含）。

    Returns:
        落入区间内的转写片段列表，按输入顺序排列。

    Raises:
        ValueError: 片段结构非法或必填字段类型不匹配时抛出。
    """
    result: list[dict[str, Any]] = []
    for index, item in enumerate(segments):
        if not isinstance(item, dict):
            raise ValueError(f"segments[{index}] 必须是对象。")
        segment_start = _require_number(item.get("start_seconds"), f"segments[{index}].start_seconds")
        segment_end = _require_number(item.get("end_seconds"), f"segments[{index}].end_seconds")
        text = _require_text(item.get("text"), f"segments[{index}].text")
        if segment_end < start or segment_start > end:
            continue
        result.append({"start_seconds": segment_start, "end_seconds": segment_end, "text": text})
    return result


def _require_text(value: object, label: str) -> str:
    """校验 `value` 是非空字符串，自动 `strip`。

    Args:
        value: 待校验值。
        label: 字段路径，仅用于错误信息展示。

    Returns:
        去除首尾空白后的字符串。

    Raises:
        ValueError: `value` 不是字符串或去除空白后为空时抛出。
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空字符串。")
    return value.strip()


def _require_number(value: object, label: str) -> float:
    """校验 `value` 是 `int` 或 `float`，并归一为 `float`。

    Args:
        value: 待校验值。
        label: 字段路径，仅用于错误信息展示。

    Returns:
        转成 `float` 后的值。

    Raises:
        ValueError: `value` 不是 `int`/`float`（不含 `bool`）时抛出。
    """
    if not isinstance(value, int | float):
        raise ValueError(f"{label} 必须是数字。")
    return float(value)


def _require_list(value: object, label: str) -> list[object]:
    """校验 `value` 是 `list`（不做元素层面的校验）。

    Args:
        value: 待校验值。
        label: 字段路径，仅用于错误信息展示。

    Returns:
        原样的 `list`。

    Raises:
        ValueError: `value` 不是 `list` 时抛出。
    """
    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是数组。")
    return value


def _require_text_list(value: object, label: str) -> list[str]:
    """校验 `value` 是元素皆为非空字符串的 `list[str]`。

    Args:
        value: 待校验值。
        label: 字段路径，用于错误信息展示；下标会拼成 `label[0]` 形式。

    Returns:
        已 `strip` 的字符串列表。

    Raises:
        ValueError: `value` 不是列表，或任一元素不是非空字符串时抛出。
    """
    items = _require_list(value, label)
    result = []
    for index, item in enumerate(items):
        result.append(_require_text(item, f"{label}[{index}]"))
    return result
