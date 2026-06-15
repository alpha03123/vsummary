"""单视频总结生成用例（生成层编排核心）。

按 `探测 → 抽音频 → 转写 → （可选）增强 → 落转写 → LLM 总结 → 提交`
的流水线把视频转换为结构化总结文档。中间产物全部在 staging 目录
下生成，最终通过原子 move 提交到 `output_dir`，保证失败时不会
污染既有制品。

进度上报：
- 阶段名（`stage`）：`probe` / `extract_audio` / `transcribe` /
  `enhance_transcript` / `summarize`；
- 转写阶段会按 0.0-1.0 的 ratio 把进度插值到 20%-75% 区间；
- 失败/取消会被翻译为 SSE 事件，由 `ProgressReporter` 实现方路由。

错误处理与重试：
- 不做自动重试；调用方如需重试应重新触发整个用例；
- LLM 阶段的异常会被包装为带中文错误信息的 `RuntimeError`，
  若底层是连接错误，会附带「请检查 Base URL」提示；
- 取消信号来自 `ProgressReporter.is_cancel_requested` 或外部
  传入的 `GenerationCancellationContext`，触发后会中断正在进行
  的 LLM 调用与子进程，staging 目录会被清理。
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
import shutil
from uuid import uuid4

from backend.video_summary.domain.models import SummaryDocument, VideoAsset
from backend.video_summary.generation.cancellation import GenerationCancellationContext
from backend.video_summary.generation.ports import (
    GenerationArtifactStore,
    MediaProcessor,
    ProgressReporter,
    Summarizer,
    TranscriptEnhancer,
    Transcriber,
)
from backend.video_summary.generation.stage_cache import GenerationStageCache


class GenerateCancelledError(RuntimeError):
    """生成任务被用户取消时抛出的业务异常。"""


class GenerateVideoSummary:
    """单视频总结生成用例（生成层核心编排）。

    编排流水线（任一阶段被取消都会立刻中断后续步骤）：
    1. `probe_duration` 获取视频时长；
    2. `extract_audio` 从视频抽取音频（按媒体实现身份做缓存复用）；
    3. `transcribe` 转写音频为 `Transcript`（按转写实现身份做缓存复用）；
    4. 可选 `enhance` 用 LLM 修正 ASR 噪声（按增强实现身份做缓存复用）；
    5. 落盘「增强后转写」「清洗后转写」；
    6. `summarize` 调用 LLM 生成 `SummaryDocument`；
    7. 落盘总结文档，并把 staging 目录原子提交到 `output_dir`。

    持久化 vs 临时：
    - 持久化：`output_dir` 下的制品（仅在第 7 步原子提交后可见）；
    - 临时：`staging_dir` 下的中间文件（任一阶段失败/取消都会被清理）；
    - 缓存：`output_dir/.cache`（按 manifest 复用，下一次同视频可跳过）。
    """

    def __init__(
        self,
        media_processor: MediaProcessor,
        transcriber: Transcriber,
        transcript_enhancer: TranscriptEnhancer | None,
        summarizer: Summarizer,
        artifact_store: GenerationArtifactStore,
    ) -> None:
        """注入媒体处理、转写、（可选）转写增强、总结与制品落盘端口。

        Args:
            media_processor: 用于探测时长与抽取音频的端口。
            transcriber: 同步转写端口（实现内自行管理线程）。
            transcript_enhancer: 可选的转写增强端口；为 `None` 时跳过
                「AI 修正」阶段。
            summarizer: LLM 总结端口。
            artifact_store: 制品落盘端口。
        """
        self._media_processor = media_processor
        self._transcriber = transcriber
        self._transcript_enhancer = transcript_enhancer
        self._summarizer = summarizer
        self._artifact_store = artifact_store

    async def run(
        self,
        video_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
        cancellation: GenerationCancellationContext | None = None,
    ) -> SummaryDocument:
        """为指定视频生成结构化总结文档。

        Args:
            video_path: 视频源文件路径。
            output_dir: 制品最终写入目录。
            progress_reporter: 可选进度上报端口；为 `None` 时不进行 SSE 上报。
            cancellation: 可选的外部取消上下文；为 `None` 且提供了
                `progress_reporter` 时会自动创建一个，并把 reporter 的
                `is_cancel_requested` 镜像到内部 `GenerationCancellationContext`。

        Returns:
            最终生成的结构化 `SummaryDocument`。

        Raises:
            GenerateCancelledError: 用户取消生成时抛出。
            RuntimeError: LLM 阶段异常会被包装为带中文提示的 `RuntimeError`。
            LookupError: 底层端口抛出的「无制品」错误。
        """
        resolved_cancellation = cancellation
        cancel_watch_task: asyncio.Task[None] | None = None
        if resolved_cancellation is None and progress_reporter is not None:
            resolved_cancellation = GenerationCancellationContext(str(output_dir))
            cancel_watch_task = asyncio.create_task(
                _mirror_progress_cancellation(progress_reporter, resolved_cancellation)
            )

        try:
            return await self._run_with_cancellation(
                video_path=video_path,
                output_dir=output_dir,
                progress_reporter=progress_reporter,
                cancellation=resolved_cancellation,
            )
        finally:
            if cancel_watch_task is not None:
                cancel_watch_task.cancel()
                with suppress(asyncio.CancelledError):
                    await cancel_watch_task

    async def _run_with_cancellation(
        self,
        *,
        video_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None,
        cancellation: GenerationCancellationContext | None,
    ) -> SummaryDocument:
        """前置取消检查 → 准备 staging 目录 → 跑核心流水线 → 清理 staging。

        任何阶段失败/取消都会通过 `finally` 清理 staging 目录，
        确保既有 `output_dir` 不会被污染。
        """
        _raise_if_cancelled(progress_reporter)
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)
        staging_dir = output_dir.parent / f".{output_dir.name}.generation-{uuid4().hex}.tmp"
        await asyncio.to_thread(staging_dir.mkdir, parents=True, exist_ok=False)
        try:
            return await self._run_to_staging(
                video_path=video_path,
                output_dir=output_dir,
                staging_dir=staging_dir,
                progress_reporter=progress_reporter,
                cancellation=cancellation,
            )
        finally:
            await asyncio.to_thread(_remove_tree_if_exists, staging_dir)

    async def _run_to_staging(
        self,
        *,
        video_path: Path,
        output_dir: Path,
        staging_dir: Path,
        progress_reporter: ProgressReporter | None,
        cancellation: GenerationCancellationContext | None,
    ) -> SummaryDocument:
        """在 staging 目录下依次跑各生成阶段，全部成功后原子提交到 `output_dir`。

        每个阶段都会：
        1. 视情况推进 `progress_reporter`；
        2. 优先尝试从 `GenerationStageCache` 复用上一次的中间产物；
        3. 在阻塞调用之前检查取消信号，避免浪费昂贵的计算。
        """
        audio_path = staging_dir / "audio.wav"
        transcript_stem = staging_dir / "transcript"
        stage_cache = GenerationStageCache(output_dir / ".cache", video_path)
        media_identity = _cache_identity(self._media_processor)
        transcriber_identity = _cache_identity(self._transcriber)
        enhancer_identity = (
            _cache_identity(self._transcript_enhancer)
            if self._transcript_enhancer is not None
            else ""
        )

        if progress_reporter is not None:
            progress_reporter.update("probe", 5.0, "正在分析视频信息")
        video = VideoAsset(
            source_path=video_path,
            title=video_path.stem,
            duration_seconds=await asyncio.to_thread(self._media_processor.probe_duration, video_path),
        )
        _raise_if_cancelled(progress_reporter)

        if progress_reporter is not None:
            progress_reporter.update("extract_audio", 15.0, "正在将视频转换为音频")
        audio_restored = await asyncio.to_thread(stage_cache.restore_audio, audio_path, identity=media_identity)
        if not audio_restored:
            await asyncio.to_thread(self._media_processor.extract_audio, video_path, audio_path, cancellation)
            _raise_if_cancelled(progress_reporter)
            await asyncio.to_thread(stage_cache.store_audio, audio_path, identity=media_identity)
        _raise_if_cancelled(progress_reporter)

        if progress_reporter is not None:
            progress_reporter.update("transcribe", 20.0, "正在使用 Whisper 转写音频")
        transcript = await asyncio.to_thread(stage_cache.load_transcript, "whisper", identity=transcriber_identity)
        if transcript is None:
            transcript = await asyncio.to_thread(
                self._transcriber.transcribe,
                audio_path,
                transcript_stem,
                None
                if progress_reporter is None
                else lambda ratio: _handle_transcribe_progress(progress_reporter, ratio),
            )
            _raise_if_cancelled(progress_reporter)
            await asyncio.to_thread(
                stage_cache.store_transcript,
                "whisper",
                transcript,
                identity=transcriber_identity,
            )
        _raise_if_cancelled(progress_reporter)

        if self._transcript_enhancer is not None:
            if progress_reporter is not None:
                progress_reporter.update("enhance_transcript", 78.0, "正在用 AI 修正转写文本")
            _raise_if_cancelled(progress_reporter)
            enhanced_transcript = await asyncio.to_thread(
                stage_cache.load_transcript,
                "transcript-enhance",
                identity=enhancer_identity,
            )
            if enhanced_transcript is None:
                try:
                    enhanced_transcript = await self._transcript_enhancer.enhance(video, transcript, cancellation)
                except GenerateCancelledError:
                    raise
                except Exception as error:
                    raise RuntimeError(_build_llm_stage_error("AI 内容增强", error)) from error
                _raise_if_cancelled(progress_reporter)
                await asyncio.to_thread(
                    stage_cache.store_transcript,
                    "transcript-enhance",
                    enhanced_transcript,
                    identity=enhancer_identity,
                )
            transcript = enhanced_transcript
            _raise_if_cancelled(progress_reporter)
            await self._artifact_store.save_enhanced_transcript(
                transcript=transcript,
                output_dir=staging_dir,
            )
            _raise_if_cancelled(progress_reporter)

        await self._artifact_store.save_cleaned_transcript(
            video=video,
            transcript=transcript,
            output_dir=staging_dir,
        )
        _raise_if_cancelled(progress_reporter)

        if progress_reporter is not None:
            progress_reporter.update("summarize", 88.0, "正在生成 AI 概况")
        _raise_if_cancelled(progress_reporter)
        try:
            summary_document = await self._summarizer.summarize(video, transcript, cancellation)
        except GenerateCancelledError:
            raise
        except Exception as error:
            raise RuntimeError(_build_llm_stage_error("AI 概况生成", error)) from error
        _raise_if_cancelled(progress_reporter)
        await self._artifact_store.save_summary_document(document=summary_document, output_dir=staging_dir)
        _raise_if_cancelled(progress_reporter)
        await asyncio.to_thread(_commit_generation_artifacts, staging_dir, output_dir)
        return summary_document


def _build_llm_stage_error(stage_label: str, error: Exception) -> str:
    """构造面向用户的中文 LLM 阶段错误信息。

    如果底层异常链路里含有连接失败迹象，会附加「请检查 Base URL」
    的提示；否则退化为 `f"{stage_label}失败：{error}"`。

    Args:
        stage_label: 阶段显示名（如「AI 概况生成」「AI 内容增强」）。
        error: 底层异常对象。

    Returns:
        中文错误信息字符串。
    """
    if _contains_connection_failure(error):
        return f"{stage_label}失败：无法连接到模型网关，请检查模型服务是否已启动，以及 provider settings 中的 Base URL 是否可用。"
    return f"{stage_label}失败：{error}"


def _cache_identity(component: object) -> str:
    """推导组件的「缓存身份」字符串，用于 stage_cache manifest。

    优先使用组件显式声明的 `cache_identity` 属性；否则退化为组件
    类型的 `module.qualname`，确保不同实现实例的身份稳定可比较。

    Args:
        component: 待推导的端口实现实例。

    Returns:
        缓存身份字符串；始终为非空。
    """
    explicit_identity = getattr(component, "cache_identity", None)
    if isinstance(explicit_identity, str) and explicit_identity.strip():
        return explicit_identity.strip()
    component_type = type(component)
    return f"{component_type.__module__}.{component_type.__qualname__}"


def _contains_connection_failure(error: BaseException) -> bool:
    """判断异常链路里是否包含连接失败的迹象。

    沿 `__cause__` / `__context__` 链遍历所有异常，对每个异常的
    `str(...)` 做小写匹配，命中任一连接失败关键字即返回 `True`。

    Args:
        error: 起始异常对象。

    Returns:
        若链路里存在连接失败迹象则为 `True`。
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).lower()
        if (
            "connection refused" in message
            or "connect call failed" in message
            or "cannot connect to host" in message
            or "connection error" in message
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def _handle_transcribe_progress(progress_reporter: ProgressReporter, ratio: float) -> None:
    """把转写器的内部 0.0-1.0 进度比换算成对外的 20%-75% 区间。

    先做一次取消检查，再以 `20.0 + ratio * 55.0` 的线性映射推进进度。

    Args:
        progress_reporter: 进度上报端口。
        ratio: 转写器内部进度（0.0-1.0）；会被夹紧后参与换算。
    """
    _raise_if_cancelled(progress_reporter)
    progress_reporter.update(
        "transcribe",
        20.0 + max(0.0, min(1.0, ratio)) * 55.0,
        "Whisper 正在转写音频",
    )


async def _mirror_progress_cancellation(
    progress_reporter: ProgressReporter,
    cancellation: GenerationCancellationContext,
) -> None:
    """把 `progress_reporter` 的取消信号镜像到 `cancellation` 上下文。

    每 50ms 轮询一次 reporter；一旦 reporter 报告取消，立即调用
    `cancellation.request_cancel()` 并退出协程。
    """
    while not cancellation.cancel_requested:
        if progress_reporter.is_cancel_requested():
            cancellation.request_cancel()
            return
        await asyncio.sleep(0.05)


def _raise_if_cancelled(progress_reporter: ProgressReporter | None) -> None:
    """若 reporter 已收到取消信号，则抛 `GenerateCancelledError`。

    Args:
        progress_reporter: 可选进度上报端口；为 `None` 时直接返回。

    Raises:
        GenerateCancelledError: reporter 处于取消态时抛出。
    """
    if progress_reporter is None:
        return
    try:
        progress_reporter.raise_if_cancelled()
    except RuntimeError as error:
        raise GenerateCancelledError(str(error) or "生成已取消") from error


def _commit_generation_artifacts(staging_dir: Path, output_dir: Path) -> None:
    """把 staging 目录里的全部产物原子提交到 `output_dir`。

    目录条目使用 `shutil.move` 整体替换（先 `rmtree` 旧目录），文件
    条目使用 `Path.replace` 原子改名。整个提交过程是同步执行的。

    Args:
        staging_dir: 临时 staging 目录（提交完成后调用方负责清理）。
        output_dir: 最终制品目录。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for source in staging_dir.iterdir():
        target = output_dir / source.name
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(source), str(target))
            continue
        source.replace(target)


def _remove_tree_if_exists(path: Path) -> None:
    """目录存在时 `shutil.rmtree` 递归删除；不存在时静默忽略。"""
    if path.exists():
        shutil.rmtree(path)
