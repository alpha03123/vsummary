from __future__ import annotations

from backend.agent.memory.context import AgentContext, ToolAvailability
from backend.agent.ports import AgentContextLoader
from backend.video_summary.library.ports import VideoLibraryReader


class WorkspaceAgentContextLoader:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def load(self, session_id: str) -> AgentContext:
        scope_type, series_id, video_id = _parse_session_id(session_id)
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
            )

        video = self._workspace.get_video_source(series.id, video_id)
        # A migrated video can retain SQL summaries/transcripts while its
        # original media Blob is unavailable. Agent content access must not
        # be coupled to preview/generation media availability.
        tools = self._workspace.get_video_workspace_tools(series.id, video_id)
        summary = self._workspace.get_video_summary(series.id, video_id)
        chapter_titles = []
        if summary is not None:
            raw_chapters = summary.summary.get("chapters", [])
            if isinstance(raw_chapters, list):
                chapter_titles = [
                    str(chapter.get("title", "")).strip()
                    for chapter in raw_chapters
                    if isinstance(chapter, dict) and str(chapter.get("title", "")).strip()
                ]
        return AgentContext(
            session_id=session_id,
            workspace_title=workspace_view.title,
            scope_type="video",
            series_id=series.id,
            series_title=series.title,
            video_id=video.video_id if video is not None else video_id,
            video_title=video.title if video is not None else next(
                (item.title for item in series.videos if item.id == video_id), video_id
            ),
            overview=_map_tool_availability(None if tools is None else tools.overview),
            mindmap=_map_tool_availability(None if tools is None else tools.mindmap),
            knowledge_cards=_map_tool_availability(None if tools is None else tools.knowledge_cards),
            notes=_map_tool_availability(None if tools is None else tools.notes),
            preview=_map_tool_availability(None if tools is None else tools.preview),
            chapter_titles=chapter_titles,
        )


def _map_tool_availability(tool) -> ToolAvailability:
    if tool is None:
        return ToolAvailability()
    return ToolAvailability(
        available=tool.available,
        generated=tool.generated,
        status=tool.status,
    )


def _parse_session_id(session_id: str) -> tuple[str, str | None, str | None]:
    # The frontend appends ``::timestamp`` when a user starts another chat in
    # the same video/series scope. That suffix names a conversation instance,
    # not a workspace resource.
    scope_key = session_id.split("::", 1)[0]
    parts = [part for part in scope_key.split("|") if part]
    if not parts:
        return "series", None, None

    scope_type = parts[0]
    if scope_type == "series":
        return "series", parts[1] if len(parts) > 1 else None, None
    if scope_type == "video":
        return "video", parts[1] if len(parts) > 1 else None, parts[2] if len(parts) > 2 else None
    return "series", None, None
