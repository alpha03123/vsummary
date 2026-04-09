from __future__ import annotations

import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ReportMeta:
    title: str
    workspace: Path
    started_at: datetime
    finished_at: datetime
    script: str
    args: list[str]


@dataclass(frozen=True)
class CaseReportItem:
    case_id: str
    title: str
    session_id: str
    message: str
    review_focus: str
    status: str  # ok | error
    duration_seconds: float
    event_order: list[str]
    thinking_summaries: list[str]
    tool_rows: list[str]
    final_answer: str
    raw_events: list[object] | None
    error_type: str | None
    error_message: str | None
    error_traceback: str | None

    @staticmethod
    def from_exception(
        *,
        case_id: str,
        title: str,
        session_id: str,
        message: str,
        review_focus: str,
        duration_seconds: float,
        exc: BaseException,
    ) -> "CaseReportItem":
        return CaseReportItem(
            case_id=case_id,
            title=title,
            session_id=session_id,
            message=message,
            review_focus=review_focus,
            status="error",
            duration_seconds=duration_seconds,
            event_order=[],
            thinking_summaries=[],
            tool_rows=[],
            final_answer="",
            raw_events=None,
            error_type=type(exc).__name__,
            error_message=str(exc),
            error_traceback="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).rstrip(),
        )


def render_markdown_report(
    meta: ReportMeta,
    items: list[CaseReportItem],
    *,
    include_raw_events: bool,
) -> str:
    lines: list[str] = []
    lines.append(f"# {meta.title}")
    lines.append("")
    lines.append("## 运行信息")
    lines.append(f"- workspace: `{meta.workspace}`")
    lines.append(f"- script: `{meta.script}`")
    lines.append(f"- args: `{_join_args(meta.args)}`")
    lines.append(f"- started_at: `{meta.started_at.isoformat()}`")
    lines.append(f"- finished_at: `{meta.finished_at.isoformat()}`")
    lines.append(f"- duration_seconds: `{(meta.finished_at - meta.started_at).total_seconds():.3f}`")
    lines.append("")

    ok_count = sum(1 for item in items if item.status == "ok")
    error_count = sum(1 for item in items if item.status != "ok")

    lines.append("## 汇总")
    lines.append(f"- cases_total: `{len(items)}`")
    lines.append(f"- ok: `{ok_count}`")
    lines.append(f"- error: `{error_count}`")
    lines.append("")

    lines.append("## 用例状态表")
    lines.append("| case_id | title | status | duration_s | tools | thinking | answer_len | note |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | --- |")
    for item in items:
        answer_len = len(item.final_answer or "")
        note = ""
        if item.status != "ok":
            note = f"{item.error_type}: {item.error_message}".strip(": ").replace("\n", " ")
        elif answer_len == 0:
            note = "final_answer 为空"
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(item.case_id),
                    _md_cell(item.title),
                    _md_cell(item.status),
                    f"{item.duration_seconds:.3f}",
                    str(len(item.tool_rows)),
                    str(len(item.thinking_summaries)),
                    str(answer_len),
                    _md_cell(note),
                ]
            )
            + " |"
        )
    lines.append("")

    lines.append("## 人工评审 Checklist")
    lines.append("- [ ] 是否调用了明显不该调用的工具。")
    lines.append("- [ ] 是否出现空回答、半截回答、重复回答。")
    lines.append("- [ ] 是否泄漏了内部字段，如 tool_name、payload、selected_tool。")
    lines.append("- [ ] 复杂问题下是否只是分点复述，而没有真正回答用户问题。")
    lines.append("- [ ] video 上下文问其他视频时，是否越界胡答。")
    lines.append("- [ ] 超范围问题时，是否自然拒答，而不是输出僵硬模板。")
    lines.append("")

    lines.append("## 逐用例详情")
    for item in items:
        lines.append(f"### [{item.case_id}] {item.title}")
        lines.append(f"- status: `{item.status}`")
        lines.append(f"- duration_seconds: `{item.duration_seconds:.3f}`")
        lines.append(f"- session_id: `{item.session_id}`")
        lines.append(f"- message: `{item.message}`")
        lines.append(f"- review_focus: {item.review_focus}")
        if item.status != "ok":
            lines.append(f"- error: `{item.error_type}: {item.error_message}`".rstrip())
            if item.error_traceback:
                lines.append("")
                lines.append("```")
                lines.append(item.error_traceback)
                lines.append("```")
            lines.append("")
            continue

        lines.append(f"- event_order: `{item.event_order}`")
        lines.append("")
        lines.append("#### 思路摘要")
        if item.thinking_summaries:
            for index, summary in enumerate(item.thinking_summaries, start=1):
                lines.append(f"- [{index}] {summary}")
        else:
            lines.append("- (无)")
        lines.append("")
        lines.append("#### 工具轨迹")
        if item.tool_rows:
            for row in item.tool_rows:
                lines.append(row)
        else:
            lines.append("- (无)")
        lines.append("")
        lines.append("#### 最终回答")
        lines.append("```")
        lines.append(item.final_answer or "(空)")
        lines.append("```")
        if include_raw_events and item.raw_events is not None:
            lines.append("")
            lines.append("#### 原始事件")
            lines.append("```")
            for ev in item.raw_events:
                lines.append(str(ev))
            lines.append("```")
        lines.append("")

        lines.append("#### 评审记录 (人工填写)")
        lines.append("- [ ] 通过")
        lines.append("- [ ] 不通过")
        lines.append("- 备注：")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_text_report(report_path: str, content: str) -> None:
    path = Path(report_path).expanduser()
    parent = path.parent
    if parent and not parent.exists():
        raise SystemExit(f"report_path 上级目录不存在: {parent}")
    path.write_text(content, encoding="utf-8")


def _md_cell(value: str) -> str:
    # Markdown table cell escape: keep it simple, avoid breaking the table.
    return (value or "").replace("\n", " ").replace("|", "\\|")


def _join_args(args: list[str]) -> str:
    return " ".join(item for item in args if item)

