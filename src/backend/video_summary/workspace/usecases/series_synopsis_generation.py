from __future__ import annotations

from datetime import datetime, timezone

from backend.video_summary.workspace.index_ports import WorkspaceIndexRefresher
from backend.video_summary.workspace.ports import VideoLibraryReader


def build_series_catalog_payload(
    workspace: VideoLibraryReader,
    series_id: str,
    *,
    updated_at: str | None = None,
) -> dict[str, object]:
    series = next((item for item in workspace.list_series() if item.id == series_id), None)
    if series is None:
        raise LookupError(f"series not found '{series_id}'")

    videos: list[dict[str, object]] = []
    for video in series.videos:
        summary = workspace.get_video_summary(series_id, video.id)
        if summary is None:
            videos.append(
                {
                    "video_id": video.id,
                    "title": video.title,
                    "one_sentence_summary": "",
                    "chapter_titles": [],
                    "processed": video.processed,
                }
            )
            continue

        payload = summary.summary if isinstance(summary.summary, dict) else {}
        chapter_titles = [
            str(chapter.get("title", "")).strip()
            for chapter in payload.get("chapters", [])
            if isinstance(chapter, dict) and str(chapter.get("title", "")).strip()
        ]
        videos.append(
            {
                "video_id": video.id,
                "title": summary.title,
                "one_sentence_summary": str(payload.get("one_sentence_summary", "")).strip(),
                "chapter_titles": chapter_titles,
                "processed": video.processed,
            }
        )

    return {
        "series_id": series.id,
        "series_title": series.title,
        "videos": videos,
        "updated_at": updated_at or _now_iso(),
    }


class RefreshSeriesKnowledgeMemory:
    def __init__(
        self,
        *,
        workspace,
        index_refresher: WorkspaceIndexRefresher,
    ) -> None:
        self._workspace = workspace
        self._index_refresher = index_refresher

    def refresh(self, series_id: str, video_id: str) -> None:
        catalog = build_series_catalog_payload(self._workspace, series_id)
        self._workspace.save_series_catalog(series_id, catalog)
        self._index_refresher.upsert_video(series_id, video_id)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
