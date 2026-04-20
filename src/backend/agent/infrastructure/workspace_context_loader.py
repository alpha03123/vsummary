from __future__ import annotations

from backend.agent.memory.context import AgentContext, ToolAvailability
from backend.agent.ports import AgentContextLoader
from backend.video_summary.library.ports import VideoWorkspace


class WorkspaceAgentContextLoader:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def load(self, session_id: str) -> AgentContext:
        scope_type, series_id, video_id, selected_tool = _parse_session_id(session_id)
        workspace_view = self._workspace.get_workspace()

        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        if series is None:
            raise RuntimeError("当前缺少有效的 series 上下文，无法建立 Agent 会话。")

        if scope_type == "series" or not video_id:
            return AgentContext(
                session_id=session_id,
                workspace_title=workspace_view.title,
                scope_type="series",
                series_id=series.id,
                series_title=series.title,
                selected_tool=selected_tool or "series-home",
            )

        video = self._workspace.get_video_source(series.id, video_id)
        tools = self._workspace.get_video_workspace_tools(series.id, video_id) if video is not None else None
        summary = self._workspace.get_video_summary(series.id, video_id) if video is not None else None
        chapter_titles = []
        if summary is not None:
            raw_chapters = summary.summary.get("chapters", [])
            if isinstance(raw_chapters, list):
                chapter_titles = [
                    str(chapter.get("title", "")).strip()
                    for chapter in raw_chapters
                    if isinstance(chapter, dict) and str(chapter.get("title", "")).strip()
                ]
        evidence_history = _build_video_evidence_history(summary)

        return AgentContext(
            session_id=session_id,
            workspace_title=workspace_view.title,
            scope_type="video",
            series_id=series.id,
            series_title=series.title,
            video_id=video.video_id if video is not None else video_id,
            video_title=video.title if video is not None else video_id,
            selected_tool=selected_tool or "studio",
            overview=_map_tool_availability(None if tools is None else tools.overview),
            mindmap=_map_tool_availability(None if tools is None else tools.mindmap),
            knowledge_cards=_map_tool_availability(None if tools is None else tools.knowledge_cards),
            notes=_map_tool_availability(None if tools is None else tools.notes),
            preview=_map_tool_availability(None if tools is None else tools.preview),
            chapter_titles=chapter_titles,
            evidence_history=evidence_history,
        )


def _map_tool_availability(tool) -> ToolAvailability:
    if tool is None:
        return ToolAvailability()
    return ToolAvailability(
        available=tool.available,
        generated=tool.generated,
        status=tool.status,
    )


def _build_video_evidence_history(summary) -> dict[str, object]:
    if summary is None:
        return {}
    return {
        "video_summary": {
            "series_id": summary.series_id,
            "video_id": summary.video_id,
            "title": summary.title,
            "summary": summary.summary if isinstance(summary.summary, dict) else {},
        }
    }


def _parse_session_id(session_id: str) -> tuple[str, str | None, str | None, str | None]:
    parts = [part for part in session_id.split("|") if part]
    if not parts:
        return "series", None, None, "series-home"

    scope_type = parts[0]
    if scope_type == "series":
        return "series", parts[1] if len(parts) > 1 else None, None, parts[2] if len(parts) > 2 else "series-home"
    if scope_type == "video":
        return (
            "video",
            parts[1] if len(parts) > 1 else None,
            parts[2] if len(parts) > 2 else None,
            parts[3] if len(parts) > 3 else "studio",
        )
    return "series", None, None, "series-home"
