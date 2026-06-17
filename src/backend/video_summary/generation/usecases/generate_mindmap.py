"""视频思维导图生成用例。

基于已有的总结数据生成思维导图节点/边数据，并写入制品目录。
本用例不依赖转写与音视频处理，仅消费 `MindmapGenerator` 端口的
纯函数式结果。
"""

from __future__ import annotations

from pathlib import Path

from backend.video_summary.generation.ports import GenerationArtifactStore, MindmapGenerator


class GenerateMindmap:
    """思维导图生成的用例（单视频）。

    业务场景：在视频已经生成总结数据后，用户/调度逻辑触发一次
    思维导图补全；本用例串起「生成 → 落盘」两个步骤，不感知转写。
    """

    def __init__(self, generator: MindmapGenerator, artifact_store: GenerationArtifactStore) -> None:
        """注入生成端口与制品落盘端口。"""
        self._generator = generator
        self._artifact_store = artifact_store

    async def run(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
        output_dir: Path,
        transcript_text: str = "",
    ) -> dict[str, object]:
        """基于总结数据生成思维导图并落盘。

        Args:
            title: 视频标题，用于思维导图根节点。
            duration_seconds: 视频时长（秒），用于时间锚点。
            summary_data: 已生成的总结结构化数据，作为思维导图骨架。
            output_dir: 思维导图制品的写入目录。
            transcript_text: 转写文本，用于 LLM 提取更多层级细节。

        Returns:
            写入磁盘的思维导图节点/边字典（与生成端口返回值一致）。
        """
        mindmap = await self._generator.generate(
            title=title,
            duration_seconds=duration_seconds,
            summary_data=summary_data,
            transcript_text=transcript_text,
        )
        await self._artifact_store.save_mindmap(mindmap=mindmap, output_dir=output_dir)
        return mindmap
