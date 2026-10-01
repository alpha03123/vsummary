from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.local.http.app import create_app
from backend.video_summary.infrastructure.persistence.models import ExternalMediaReference
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.usecases import ListVideoLibrary
from tests._api_fixtures import make_api_container, make_workspace_services


@pytest.mark.parametrize("downloaded", [False, True], ids=["linked", "downloaded"])
def test_library_preserves_platform_identity_and_part_after_reload(stored_video, mysql_sessions, tmp_path, downloaded) -> None:
    workspace, _, _ = stored_video
    inbox_id = workspace.ensure_bilibili_inbox_series()
    bvid = "BV1example"
    linked_videos = [
        LinkedVideo(
            source_id=bvid, item_index=part, title=f"Part {part}", cover_url="", duration_seconds=60,
            source_url=f"https://www.bilibili.com/video/{bvid}?p={part}",
        )
        for part in (1, 2)
    ]
    workspace.save_linked_series(LinkedSeries(
        series_id=inbox_id, title="B站导入", cover_url="", source_url="", videos=linked_videos,
    ))
    before = next(series for series in workspace.list_series() if series.id == inbox_id)
    saved_ids = [video.id for video in sorted(before.videos, key=lambda video: video.title)]
    if downloaded:
        media = tmp_path / "downloaded.mp4"
        media.write_bytes(b"downloaded media")
        with mysql_sessions.begin() as session:
            session.add_all(ExternalMediaReference(video_id=video_id, source_path=str(media)) for video_id in saved_ids)

    container = make_api_container(services=make_workspace_services(
        workspace_id=workspace.workspace_id, list_video_library=ListVideoLibrary(workspace),
    ))
    response = TestClient(create_app(container)).get("/api/videos")
    assert response.status_code == 200
    inbox = next(series for series in response.json()["series"] if series["id"] == inbox_id)
    assert inbox["kind"] == "bilibili_inbox"
    cards = sorted(inbox["videos"], key=lambda card: card["title"])
    assert [card["id"] for card in cards] == saved_ids
    assert [card["source_id"] for card in cards] == [bvid, bvid]
    assert [card["item_index"] for card in cards] == [1, 2]
    assert [card["source_url"] for card in cards] == [video.source_url for video in linked_videos]
    assert [card["provider"] for card in cards] == ["bilibili", "bilibili"]
    assert all(card["is_linked"] is not downloaded for card in cards)
    assert all(card["source_type"] == "video" for card in cards)
