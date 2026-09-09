"""可由 yt-dlp 驱动的外部视频平台适配器。"""

from backend.external.ytdlp import (
    BackgroundYtDlpDownloadStarter,
    DrissionCookieInitializer,
    YtDlpLinkedVideoDownloadStarter,
    YtDlpPlatform,
    YtDlpPlatformDownloader,
    YtDlpPlatformResolver,
)

__all__ = [
    "DrissionCookieInitializer",
    "BackgroundYtDlpDownloadStarter",
    "YtDlpLinkedVideoDownloadStarter",
    "YtDlpPlatform",
    "YtDlpPlatformDownloader",
    "YtDlpPlatformResolver",
]
