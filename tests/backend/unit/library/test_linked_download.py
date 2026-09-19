from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.usecases.linked_videos import StartLinkedVideoDownload


class _Workspace:
    def __init__(self) -> None:
        self.video = LinkedVideo(
            source_id="BV1example",
            item_index=1,
            title="Linked video",
            cover_url="",
            duration_seconds=1,
            source_url="https://www.bilibili.com/video/BV1example",
        )

    def get_linked_video_for_download(self, series_id: str, video_id: str):
        if (series_id, video_id) == ("series-ulid", "video-ulid"):
            return self.video
        return None


class _Starter:
    def __init__(self) -> None:
        self.received = None

    def start(self, *, series_id: str, video: LinkedVideo) -> str:
        self.received = (series_id, video)
        return f"download/{series_id}/{video.video_id}"


def test_download_resolves_library_video_id_to_external_metadata() -> None:
    workspace = _Workspace()
    starter = _Starter()

    result = StartLinkedVideoDownload(workspace, starter).run(
        series_id="series-ulid",
        video_id="video-ulid",
    )

    assert result.task_id == "download/series-ulid/BV1example"
    assert starter.received == ("series-ulid", workspace.video)
