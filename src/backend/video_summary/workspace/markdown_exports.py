from __future__ import annotations

from typing import Any

from backend.video_summary.summary_generation.prompts import format_timestamp


def render_transcript_markdown(payload: dict[str, Any]) -> str:
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
    title = _require_text(payload.get("title"), "title")
    cards = _require_list(payload.get("cards"), "cards")

    lines = [f"# {title} 知识卡片", ""]
    for index, item in enumerate(cards):
        if not isinstance(item, dict):
            raise ValueError(f"cards[{index}] 必须是对象。")
        lines.extend(_render_knowledge_card(item, index))

    return "\n".join(lines).strip() + "\n"


def render_notes_markdown(title: str, payload: dict[str, Any]) -> str:
    notes = _require_list(payload.get("notes"), "notes")
    lines = [f"# {_require_text(title, 'title')} 笔记", ""]
    for index, item in enumerate(notes):
        if not isinstance(item, dict):
            raise ValueError(f"notes[{index}] 必须是对象。")
        lines.extend(_render_note(item, index))
    return "\n".join(lines).strip() + "\n"


def render_mixed_overview_markdown(summary_payload: dict[str, Any], transcript_payload: dict[str, Any]) -> str:
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
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空字符串。")
    return value.strip()


def _require_number(value: object, label: str) -> float:
    if not isinstance(value, int | float):
        raise ValueError(f"{label} 必须是数字。")
    return float(value)


def _require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是数组。")
    return value


def _require_text_list(value: object, label: str) -> list[str]:
    items = _require_list(value, label)
    result = []
    for index, item in enumerate(items):
        result.append(_require_text(item, f"{label}[{index}]"))
    return result
