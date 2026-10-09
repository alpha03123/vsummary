"""Product-composition adapter for durable linked-video download jobs."""

from __future__ import annotations

from pathlib import Path

from backend.bilibili import BilibiliDownloader
from backend.chaoxing import ChaoxingDownloaderClient
from backend.external import YtDlpPlatformDownloader
from backend.video_summary.library.linked_models import LinkedVideo
from backend.video_summary.library.ports import LinkedVideoDownloader


class ProviderLinkedVideoDownloader:
    """Runs provider IO synchronously while the Job Worker owns lifecycle state."""

    def __init__(
        self,
        *,
        download_root: Path,
        bilibili_downloader: BilibiliDownloader,
        platform_downloaders: dict[str, YtDlpPlatformDownloader],
        chaoxing_client: ChaoxingDownloaderClient,
        overrides: dict[str, LinkedVideoDownloader] | None = None,
    ) -> None:
        self._download_root = download_root
        self._bilibili_downloader = bilibili_downloader
        self._platform_downloaders = platform_downloaders
        self._chaoxing_client = chaoxing_client
        self._overrides = dict(overrides or {})

    def download(self, *, series_id: str, video: LinkedVideo, reporter) -> Path:
        if video.provider in self._overrides:
            return self._overrides[video.provider].download(series_id=series_id, video=video, reporter=reporter)
        destination = self._download_root / series_id / video.video_id
        if video.provider == "bilibili":
            return self._bilibili_downloader.download(video.source_id, video.item_index, destination, reporter)
        if video.provider == "chaoxing":
            if not video.download_key:
                raise ValueError(f"chaoxing linked video missing download_key: {video.video_id}")
            reporter.update("download", 0.0, "开始下载超星视频")
            path = self._chaoxing_client.download_video(
                video.download_key,
                output_dir=destination,
                filename=f"{video.video_id}.mp4",
                progress=lambda downloaded, total: _report_chaoxing_progress(reporter, downloaded, total),
            )
            return Path(path)
        downloader = self._platform_downloaders.get(video.provider)
        if downloader is None:
            raise ValueError(f"unsupported linked video provider '{video.provider}'")
        return downloader.download(video, destination, reporter)


def _report_chaoxing_progress(reporter, downloaded: int, total: int | None) -> None:
    reporter.raise_if_cancelled()
    if total and total > 0:
        progress = max(0.0, min(100.0, downloaded / total * 100.0))
        reporter.update("download", progress, f"下载中 {progress:.1f}%")
        return
    reporter.update("download", None, f"已下载 {downloaded} bytes")
