"""本地视频导入用例集合。

把"把磁盘上的视频文件纳入视频库"这一组操作封装为独立的用例，作为 API 路由
与导入 UI 之间的中间层；具体文件复制与卡片生成由 `VideoImportStore` 实现完成。
"""

from __future__ import annotations

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

    def run(self, *, title: str, files: list[tuple[str, object]]) -> LibrarySeriesDTO:
        """执行导入并返回新建系列的 DTO。

        Args:
            title: 新系列的展示标题。
            files: 待导入的本地文件条目列表，每项为 `(文件名, 文件对象)` 元组
                （文件对象的具体形态由实现侧决定，例如路径或可读流）。

        Returns:
            包含新系列 ID、标题与视频卡片列表的 `LibrarySeriesDTO`。
        """
        return self._workspace.import_local_series(title=title, files=files)


class ImportLocalPlaygroundVideos:
    """把本地视频导入到内置的"沙盒演练"系列中。

    业务场景：用户尚未决定如何归类视频时，先丢进沙盒系列以便快速试做
    转写/总结；沙盒系列是固定 ID 的特殊系列，导入后用户可继续把它移入正式系列。
    """

    def __init__(self, workspace: VideoImportStore) -> None:
        """通过 `VideoImportStore` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self, *, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        """执行导入并返回沙盒系列下的视频卡片列表。

        Args:
            files: 待导入的本地文件条目列表，每项为 `(文件名, 文件对象)` 元组。

        Returns:
            新加入沙盒系列的视频卡片 DTO 列表。
        """
        return self._workspace.import_local_playground_videos(files=files)


class ImportLocalSeriesVideos:
    """把本地视频追加到既有系列。

    业务场景：用户已有系列，需要把新一批本地视频挂到该系列下，而不必新建系列；
    该用例保证新视频与系列元数据正确绑定。
    """

    def __init__(self, workspace: VideoImportStore) -> None:
        """通过 `VideoImportStore` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self, *, series_id: str, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        """执行追加并返回新增的视频卡片列表。

        Args:
            series_id: 既有系列唯一 ID。
            files: 待追加的本地文件条目列表，每项为 `(文件名, 文件对象)` 元组。

        Returns:
            追加完成后新加入的视频卡片 DTO 列表。
        """
        return self._workspace.import_local_series_videos(series_id=series_id, files=files)
