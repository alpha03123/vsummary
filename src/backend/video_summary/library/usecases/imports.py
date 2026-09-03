"""本地视频导入用例集合。

把"把磁盘上的视频文件纳入视频库"这一组操作封装为独立的用例，作为 API 路由
与导入 UI 之间的中间层；具体文件复制与卡片生成由 `VideoImportStore` 实现完成。
"""

from __future__ import annotations

from pathlib import Path

from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO
from backend.video_summary.library.ports import VideoImportStore


class ImportLocalSeries:
    """新建一个本地视频系列并导入给定文件。

    业务场景：用户在工作区里首次组织一批视频时，用此用例落地一个新系列
    （含标题与一组原始视频文件）；副作用是在磁盘上建立系列目录与源文件副本。
    """

    def __init__(self, workspace: VideoImportStore) -> None:
        """通过 `VideoImportStore` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run_from_paths(
        self,
        *,
        title: str,
        source_paths: list[Path],
        storage_mode: str,
    ) -> LibrarySeriesDTO:
        """从本机绝对路径创建系列。"""
        return self._workspace.import_local_series_from_paths(
            title=title,
            source_paths=source_paths,
            storage_mode=storage_mode,
        )


class ImportLocalPlaygroundVideos:
    """把本地视频导入到内置的"沙盒演练"系列中。

    业务场景：用户尚未决定如何归类视频时，先丢进沙盒系列以便快速试做
    转写/总结；沙盒系列是固定 ID 的特殊系列，导入后用户可继续把它移入正式系列。
    """

    def __init__(self, workspace: VideoImportStore) -> None:
        """通过 `VideoImportStore` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run_from_paths(self, *, source_paths: list[Path]) -> list[LibraryVideoCardDTO]:
        """从本机绝对路径向沙盒追加媒体。"""
        return self._workspace.import_local_playground_videos_from_paths(source_paths=source_paths)


class ImportLocalSeriesVideos:
    """把本地视频追加到既有系列。

    业务场景：用户已有系列，需要把新一批本地视频挂到该系列下，而不必新建系列；
    该用例保证新视频与系列元数据正确绑定。
    """

    def __init__(self, workspace: VideoImportStore) -> None:
        """通过 `VideoImportStore` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run_from_paths(self, *, series_id: str, source_paths: list[Path]) -> list[LibraryVideoCardDTO]:
        """从本机绝对路径向系列追加媒体。"""
        return self._workspace.import_local_series_videos_from_paths(
            series_id=series_id,
            source_paths=source_paths,
        )
