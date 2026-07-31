"""生成层 Markdown 渲染器。

把 LLM 产出的结构化 `summary_data` 渲染为可直接给前端阅读的
Markdown 文本，章节、要点、关键结论均按统一模板拼接。
"""

from __future__ import annotations

from typing import Any
import re

from .prompts import format_timestamp


def render_markdown(summary_data: dict[str, Any]) -> str:
    """把结构化总结数据渲染为 Markdown 文本。

    渲染顺序：标题 → 一句话总结 → 核心问题 → 章节摘要（每个章节含
    时间区间、锚点、摘要与要点）→ 关键结论。章节列表为空时仍输出
    "## 章节摘要"标题，便于前端始终能定位到对应区块。

    Args:
        summary_data: LLM 产出的结构化字段，期望包含 `title`、
            `one_sentence_summary`、`core_problem`、`chapters`、
            `key_takeaways` 五个键。

    Returns:
        以换行结尾的 Markdown 字符串。
    """
    lines: list[str] = [f"# {summary_data['title']}", ""]
    lines.append("## 一句话总结")
    lines.append(summary_data["one_sentence_summary"])
    lines.append("")
    lines.append("## 核心问题")
    lines.append(summary_data["core_problem"])
    lines.append("")
    lines.append("## 章节摘要")
    lines.append("")

    for chapter in summary_data["chapters"]:
        start = format_timestamp(chapter["start_seconds"])
        end = format_timestamp(chapter["end_seconds"])
        lines.append(f"### {chapter['title']} ({start} - {end})")
        lines.append(f"<a id=\"{chapter['id']}\"></a>")
        lines.append(chapter["summary"])
        lines.append("")
        if chapter["key_points"]:
            for point in chapter["key_points"]:
                lines.append(f"- {point}")
            lines.append("")

    lines.append("## 关键结论")
    for point in summary_data["key_takeaways"]:
        lines.append(f"- {point}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def parse_markdown(markdown: str) -> dict[str, Any]:
    """严格解析 ``render_markdown`` 生成的总结 Markdown。"""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or not lines[0].startswith("# ") or lines[0].startswith("## "):
        raise ValueError("第 1 行必须是 '# 视频标题'。")
    headings = ("## 一句话总结", "## 核心问题", "## 章节摘要", "## 关键结论")
    positions: list[int] = []
    for heading in headings:
        matches = [index for index, line in enumerate(lines) if line == heading]
        if len(matches) != 1:
            raise ValueError(f"必须且只能包含一个 '{heading}' 标题。")
        positions.append(matches[0])
    if positions != sorted(positions):
        raise ValueError("总结标题必须依次为：一句话总结、核心问题、章节摘要、关键结论。")

    def section(start: int, end: int) -> list[str]:
        result = lines[start + 1:end]
        while result and not result[0].strip():
            result.pop(0)
        while result and not result[-1].strip():
            result.pop()
        return result

    chapters = _parse_markdown_chapters(section(positions[2], positions[3]))
    takeaways = _parse_markdown_bullets(section(positions[3], len(lines)), "关键结论")
    from .schemas import SummaryPayload

    return SummaryPayload.model_validate(
        {
            "title": lines[0][2:].strip(),
            "one_sentence_summary": "\n".join(section(positions[0], positions[1])).strip(),
            "core_problem": "\n".join(section(positions[1], positions[2])).strip(),
            "chapters": chapters,
            "key_takeaways": takeaways,
        }
    ).model_dump(mode="json")


def _parse_markdown_chapters(lines: list[str]) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    index = 0
    header = re.compile(r"^### (?P<title>.+) \((?P<start>\d{2}:\d{2}(?::\d{2})?) - (?P<end>\d{2}:\d{2}(?::\d{2})?)\)$")
    anchor = re.compile(r'^<a id="(?P<id>[^"]+)"></a>$')
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        match = header.fullmatch(lines[index])
        if match is None:
            raise ValueError(f"章节区第 {index + 1} 行必须是 '### 标题 (00:00 - 00:00)'。")
        if index + 1 >= len(lines) or (anchor_match := anchor.fullmatch(lines[index + 1])) is None:
            raise ValueError(f"章节 '{match.group('title')}' 后必须紧跟 <a id=\"章节 ID\"></a>。")
        index += 2
        body: list[str] = []
        points: list[str] = []
        reading_points = False
        while index < len(lines) and not lines[index].startswith("### "):
            line = lines[index]
            if line.startswith("- "):
                reading_points = True
                points.append(line[2:].strip())
            elif reading_points and line.strip():
                raise ValueError(f"章节 '{match.group('title')}' 的要点必须使用 '- ' 列表。")
            elif not reading_points:
                body.append(line)
            index += 1
        while body and not body[-1].strip():
            body.pop()
        chapters.append(
            {
                "id": anchor_match.group("id"),
                "title": match.group("title").strip(),
                "start_seconds": _parse_timestamp(match.group("start")),
                "end_seconds": _parse_timestamp(match.group("end")),
                "summary": "\n".join(body).strip(),
                "key_points": [point for point in points if point],
            }
        )
    return chapters


def _parse_markdown_bullets(lines: list[str], section_name: str) -> list[str]:
    if any(line.strip() and not line.startswith("- ") for line in lines):
        raise ValueError(f"{section_name}中的每一项必须使用 '- ' 列表。")
    return [line[2:].strip() for line in lines if line.startswith("- ") and line[2:].strip()]


def _parse_timestamp(value: str) -> float:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return float(minutes * 60 + seconds)
    hours, minutes, seconds = parts
    return float(hours * 3600 + minutes * 60 + seconds)
