"""生成层 Protocol 端口集合。

把生成子步骤（音视频处理、转写、总结、增强、思维导图、制品落盘、
进度上报）抽象为 Protocol，便于在测试中替换为假实现。具体实现
位于 `infrastructure/` 子包，本模块不依赖任何具体实现。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset

if TYPE_CHECKING:
    from backend.video_summary.generation.cancellation import GenerationCancellationContext


class MediaProcessor(Protocol):
    """音视频文件预处理端口。"""

    def probe_duration(self, video_path: Path) -> float:
        """探测视频时长（秒）。"""

    def extract_audio(
        self,
        video_path: Path,
        audio_path: Path,
        cancellation: "GenerationCancellationContext | None" = None,
    ) -> Path:
        """从视频中抽取音频到目标路径，返回实际写入的音频文件路径。"""


class Transcriber(Protocol):
    """音频转写端口（同步实现，内部自行管理线程）。"""

    def transcribe(
        self,
        audio_path: Path,
        output_stem: Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> Transcript:
        """把音频文件转写为 `Transcript`；`on_progress` 回调传入 0.0-1.0 的进度比。"""


class Summarizer(Protocol):
    """LLM 总结端口。"""

    async def summarize(
        self,
        video: VideoAsset,
        transcript: Transcript,
        cancellation: "GenerationCancellationContext | None" = None,
    ) -> SummaryDocument:
        """基于视频与转写生成结构化总结文档（含 Markdown/结构化字段/思维导图）。"""


class TranscriptEnhancer(Protocol):
    """转写增强端口（用 LLM 修正 ASR 噪声）。"""

    async def enhance(
        self,
        video: VideoAsset,
        transcript: Transcript,
        cancellation: "GenerationCancellationContext | None" = None,
    ) -> Transcript:
        """对原始转写做噪声修正与补全，返回增强后的 `Transcript`。"""


class MindmapGenerator(Protocol):
    """思维导图生成端口（纯函数式，不落盘）。"""

    async def generate(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
        transcript_text: str = "",
    ) -> dict[str, object]:
        """基于总结数据生成思维导图节点/边字典。"""


class SeriesMindmapGenerator(Protocol):
    """系列级跨视频思维导图生成端口。"""

    async def generate(
        self,
        *,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
    ) -> dict[str, object]:
        """基于系列目录与视频概况列表生成跨视频思维导图节点/边字典。"""


class GenerationArtifactStore(Protocol):
    """生成制品的落盘端口（写入视频制品目录的 JSON 等）。"""

    async def save_cleaned_transcript(
        self,
        *,
        video: VideoAsset,
        transcript: Transcript,
        output_dir: Path,
    ) -> None:
        """保存清洗后的转写制品（作为最终落盘版本之一）。"""

    async def save_enhanced_transcript(
        self,
        *,
        transcript: Transcript,
        output_dir: Path,
    ) -> None:
        """保存增强后的转写制品；未启用增强时不调用。"""

    async def save_summary_document(self, *, document: SummaryDocument, output_dir: Path) -> None:
        """保存结构化总结文档（Markdown/结构化字段/思维导图）。"""

    async def save_mindmap(self, *, mindmap: dict[str, object], output_dir: Path) -> None:
        """保存思维导图节点/边数据。"""


class ProgressReporter(Protocol):
    """生成进度的上报端口（实现侧路由到 InMemoryProgressTracker 并通过 SSE 输出）。

    进度事件按 `stage` 命名（probe/extract_audio/transcribe/...），
    `progress` 取值范围 0.0-100.0；`detail` 为可选的中文说明文本。
    """

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        """上报一次进度更新；阶段切换/进度推进时调用。"""

    def completed(self, detail: str | None = None) -> None:
        """上报任务成功完成。"""

    def failed(self, message: str) -> None:
        """上报任务失败。"""

    def cancelled(self, detail: str | None = None) -> None:
        """上报任务被取消。"""

    def is_cancel_requested(self) -> bool:
        """是否已收到取消请求；调用方应在循环中定期检查。"""

    def raise_if_cancelled(self) -> None:
        """若已取消则抛 `RuntimeError`（由用例转换为 `GenerateCancelledError`）。"""
