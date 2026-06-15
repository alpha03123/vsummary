"""生成层 Markdown 渲染器。

把 LLM 产出的结构化 `summary_data` 渲染为可直接给前端阅读的
Markdown 文本，章节、要点、关键结论均按统一模板拼接。
"""

from __future__ import annotations

from typing import Any

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
