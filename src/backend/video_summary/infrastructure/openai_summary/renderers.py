from __future__ import annotations

from typing import Any

from .prompts import format_timestamp


def render_markdown(summary_data: dict[str, Any]) -> str:
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
    lines.append("## 思维导图数据")
    lines.append("交互式思维导图请读取同目录下的 `mindmap.json`。")
    lines.append("")
    return "\n".join(lines).strip() + "\n"

