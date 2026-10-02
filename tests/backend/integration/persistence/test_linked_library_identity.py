from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import Mock

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


def test_downloaded_blob_uses_bilibili_subtitles_and_assigns_each_segment_to_one_chapter(stored_video, tmp_path, monkeypatch) -> None:
    from backend.video_summary.domain.models import SummaryDocument
    from backend.video_summary.generation.renderers import render_markdown
    from backend.video_summary.generation.schemas import SummaryPayload
    from backend.video_summary.generation.usecases.generate_summary import GenerateVideoSummary
    from backend.video_summary.infrastructure.application_builders import VideoSummaryApplication
    from backend.video_summary.infrastructure.config.settings import load_settings
    from backend.video_summary.infrastructure.persistence.sql_generation_adapters import SqlBackedVideoSummaryGenerator
    from backend.video_summary.infrastructure.storage.temporary_generation_artifact_store import TemporaryGenerationArtifactStore
    from backend.video_summary.infrastructure.subtitle_transcripts import SubtitleTranscriptProvider
    from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow

    workspace, _, _ = stored_video
    series_id = workspace.ensure_bilibili_inbox_series()
    url = "https://www.bilibili.com/video/BV1vJ3P6KEkh?p=2"
    linked = LinkedVideo(source_id="BV1vJ3P6KEkh", item_index=2, title="Part 2", cover_url="", duration_seconds=3, source_url=url)
    workspace.save_linked_series(LinkedSeries(series_id=series_id, title="Inbox", cover_url="", source_url="", videos=[linked]))
    video_id = next(series for series in workspace.list_series() if series.id == series_id).videos[0].id
    downloaded = tmp_path / "downloaded.mp4"
    downloaded.write_bytes(b"downloaded media")
    monkeypatch.setattr(workspace, "_prepare_browser_preview", lambda *args: None)
    workspace.attach_downloaded_file(series_id, video_id, downloaded)
    source = workspace.get_video_source(series_id, video_id)
    assert source.source_path.name == "source.mp4"

    requested_urls = []
    class YoutubeDL:
        def __init__(self, options):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, source_url, download):
            requested_urls.append(source_url)
            return {"subtitles": {"ai-zh": [{"ext": "srt", "data":
                "1\n00:00:00,000 --> 00:00:01,500\n第一段原文\n\n"
                "2\n00:00:01,500 --> 00:00:03,000\n第二段原文\n\n"}]}}
    monkeypatch.setattr("yt_dlp.YoutubeDL", YoutubeDL)

    class Summarizer:
        async def summarize(self, video, transcript, cancellation=None):
            payload = SummaryPayload.model_validate({"title": "Part 2", "chapters": [
                {"id": "ch-1", "title": "First", "start_seconds": 0, "end_seconds": 1.5},
                {"id": "ch-2", "title": "Second", "start_seconds": 1.5, "end_seconds": 3},
            ]}).model_dump()
            return SummaryDocument(markdown=render_markdown(payload), summary_data=payload)

    media = Mock(spec=["probe_duration", "extract_audio"])
    media.probe_duration.side_effect = AssertionError("Subtitle hit must skip probing/audio extraction")
    media.extract_audio.side_effect = AssertionError("Subtitle hit must skip audio extraction")
    asr = Mock(spec=["transcribe"])
    asr.transcribe.side_effect = AssertionError("Subtitle hit must skip ASR")
    use_case = GenerateVideoSummary(
        media_processor=media, transcriber=asr, summarizer=Summarizer(), transcript_enhancer=None,
        artifact_store=TemporaryGenerationArtifactStore(), subtitle_provider=SubtitleTranscriptProvider(),
    )
    config = tmp_path / "settings.toml"
    config.write_text((Path(__file__).resolve().parents[4] / "config" / "settings.toml.example").read_text(encoding="utf-8"), encoding="utf-8")
    application = VideoSummaryApplication(settings=load_settings(config, tmp_path), use_case=use_case)
    workflow = ConfiguredVideoSummaryWorkflow(tmp_path)
    monkeypatch.setattr(workflow, "_get_application", lambda _enabled: application)
    generator = SqlBackedVideoSummaryGenerator(workspace=workspace, workflow=workflow, temp_root=tmp_path / "tasks")
    asyncio.run(generator.run(series_id=series_id, video_id=video_id))
    asyncio.run(generator.run(series_id=series_id, video_id=video_id))

    assert requested_urls == [url]
    asr.transcribe.assert_not_called()
    chapters = workspace.get_video_summary(series_id, video_id).summary["chapters"]
    assert [[segment["text"] for segment in chapter["transcript_segments"]] for chapter in chapters] == [["第一段原文"], ["第二段原文"]]
