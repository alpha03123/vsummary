from pathlib import Path

from backend.video_summary.library.linked_models import LinkedVideo
from backend.video_summary.library.usecases.linked_videos import DownloadLinkedVideo


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
        self.attached: tuple[str, str, Path] | None = None

    def get_linked_video_for_download(self, series_id: str, video_id: str):
        return self.video if (series_id, video_id) == ("series-ulid", "video-ulid") else None

    def attach_downloaded_file(self, series_id: str, video_id: str, source_path: Path) -> None:
        self.attached = (series_id, video_id, source_path)


class _Downloader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.received = None

    def download(self, *, series_id: str, video: LinkedVideo, reporter) -> Path:
        self.received = (series_id, video, reporter)
        self.path.write_bytes(b"video")
        return self.path


class _Reporter:
    def __init__(self) -> None:
        self.updates: list[tuple[str, float | None, str | None]] = []

    def raise_if_cancelled(self) -> None:
        return None

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        self.updates.append((stage, progress, detail))


def test_download_commits_library_video_after_provider_download(tmp_path: Path) -> None:
    workspace = _Workspace()
    source_path = tmp_path / "linked.mp4"
    downloader = _Downloader(source_path)
    reporter = _Reporter()

    DownloadLinkedVideo(workspace, downloader).run(
        series_id="series-ulid",
        video_id="video-ulid",
        reporter=reporter,
    )

    assert downloader.received == ("series-ulid", workspace.video, reporter)
    assert workspace.attached == ("series-ulid", "video-ulid", source_path)
    assert reporter.updates == [("persist", 99.0, "正在保存下载的视频")]
    assert not source_path.exists()


def test_download_rejects_unknown_linked_video(tmp_path: Path) -> None:
    workspace = _Workspace()
    downloader = _Downloader(tmp_path / "linked.mp4")

    try:
        DownloadLinkedVideo(workspace, downloader).run(
            series_id="series-ulid",
            video_id="missing",
            reporter=_Reporter(),
        )
    except LookupError as error:
        assert "series-ulid/missing" in str(error)
    else:
        raise AssertionError("unknown linked video must be rejected")
