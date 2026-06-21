"""GenerateSeriesMindmap 用例。

基于系列概览和所有视频的总结数据，生成跨视频的系列级思维导图。
本用例调用 `SeriesMindmapGenerator` 端口生成节点/边数据，
然后通过 `GenerationArtifactStore` 端口落盘。
"""

from __future__ import annotations

from pathlib import Path

from backend.video_summary.generation.ports import (
    GenerationArtifactStore,
    ProgressReporter,
    SeriesMindmapGenerator,
)


class GenerateSeriesMindmap:
    """系列级思维导图生成用例。

    业务场景：在系列总结场景中，基于系列目录和各视频的总结数据，
    生成跨视频的知识结构思维导图，供查看或导出。
    """

    def __init__(self, generator: SeriesMindmapGenerator, artifact_store: GenerationArtifactStore) -> None:
        """注入生成端口与制品落盘端口。

        Args:
            generator: LLM 驱动的系列思维导图生成适配器。
            artifact_store: 用于将导图节点/边数据写入磁盘。
        """
        self._generator = generator
        self._artifact_store = artifact_store

    async def run(
        self,
        *,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
    ) -> dict[str, object]:
        """基于系列目录与视频概况生成思维导图并落盘。

        Args:
            series_title: 系列标题，作为思维导图根节点上下文。
            catalog: 系列目录数据字典（series_catalog.json 的内容）。
            video_summaries: 各视频概括列表，每项应包含 title / one_sentence_summary / chapters 等字段。
            output_dir: 思维导图制品的写入目录。
            progress_reporter: 可选进度上报端口；为 `None` 时不进行 SSE 上报。

        Returns:
            写入磁盘的思维导图节点/边字典（与生成端口返回值一致）。
        """
        if progress_reporter is not None:
            progress_reporter.update("generate", 10.0, "正在生成系列思维导图")
        mindmap = await self._generator.generate(
            series_title=series_title,
            catalog=catalog,
            video_summaries=video_summaries,
        )
        if progress_reporter is not None:
            progress_reporter.update("save", 80.0, "正在保存系列思维导图")
        await self._artifact_store.save_mindmap(mindmap=mindmap, output_dir=output_dir)
        if progress_reporter is not None:
            progress_reporter.completed("系列思维导图已生成")
        return mindmap
