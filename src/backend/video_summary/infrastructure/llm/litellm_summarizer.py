"""基于 LiteLLM 的总结生成适配器。

把 `Summarizer` 端口绑定到 LiteLLM 入口：根据上下文窗口预算自适应选择
"直接总结"或"分片并发总结 + 文档级汇总"两套路径，并支持取消传播。
"""

from __future__ import annotations

import asyncio

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset
from backend.video_summary.generation.ports import Summarizer
from backend.video_summary.generation.cancellation import GenerationCancellationContext, cancellable_await
from backend.video_summary.generation import (
    SummaryPayload,
    build_chunk_prompt,
    build_document_prompt,
    build_transcript_document_prompt,
    chunk_segments,
    render_markdown,
)


class LiteLLMCompletionSummarizer(Summarizer):
    """通过 LiteLLM 异步调用 LLM 生成结构化视频总结的实现。

    业务场景：在单视频生成流程中，需要基于转写文本生成可展示的 Markdown
    总结与结构化数据。本适配器在上下文窗口允许时直接整段总结，否则退化为
    "分片并发总结 → 文档级汇总"的两阶段流程。

    实现要点：
    - 提示词构造：根据所选路径调用 `build_transcript_document_prompt` /
      `build_chunk_prompt` / `build_document_prompt`，把视频元信息、转写
      段落或分片小结注入提示词；
    - 输出约束：使用 `SummaryPayload` Pydantic schema 强制 LLM 输出结构；
    - 取消传播：每次 LLM 调用通过 `cancellable_await` 包装，循环中再轮询
      `cancellation.cancel_requested`，取消时抛 `GenerateCancelledError`；
    - 配置：依赖外部注入的 `context_window_tokens` / `reserved_output_tokens` /
      `direct_summary_threshold_ratio` / `summary_chunk_concurrency`，本类
      不读取环境或设置。
    """

    def __init__(
        self,
        gateway: LiteLLMCompletionGateway,
        *,
        context_window_tokens: int,
        reserved_output_tokens: int,
        direct_summary_threshold_ratio: float,
        summary_chunk_concurrency: int = 1,
    ) -> None:
        """注入 LiteLLM 网关与上下文预算参数。

        Args:
            gateway: 提供 `acomplete_structured` / `acomplete_text` 的 LLM 网关。
            context_window_tokens: 模型上下文窗口大小（token）。
            reserved_output_tokens: 需要为输出预留的 token 数。
            direct_summary_threshold_ratio: 判定是否走"直接总结"路径的
                阈值（占可用上下文的比例）。
            summary_chunk_concurrency: 分片总结阶段的并发上限，至少为 1。
        """
        self._gateway = gateway
        self._context_window_tokens = context_window_tokens
        self._reserved_output_tokens = reserved_output_tokens
        self._direct_summary_threshold_ratio = direct_summary_threshold_ratio
        self._summary_chunk_concurrency = max(1, summary_chunk_concurrency)

    async def summarize(
        self,
        video: VideoAsset,
        transcript: Transcript,
        cancellation: GenerationCancellationContext | None = None,
    ) -> SummaryDocument:
        """为单个视频生成结构化总结文档。

        根据提示词 token 估算与预算的对比，自适应选择两种路径之一：
        1. 提示词能装下 → 直接调用一次结构化补全得到 `SummaryPayload`；
        2. 提示词超长 → 先并发完成各分片的小结，再调用一次文档级汇总。

        Args:
            video: 视频元信息，用于提示词构造。
            transcript: 转写结果，分片与小结的输入。
            cancellation: 可选的取消上下文；非 `None` 时每次 LLM 调用均
                包装 `cancellable_await`，并在分片循环开头检查取消信号。

        Returns:
            包含 Markdown 文本与结构化字典的 `SummaryDocument`。

        Raises:
            GenerateCancelledError: 用户取消或上下文取消信号触发时抛出。
            RuntimeError: LLM 解析失败/超时等由网关层抛出的错误会原样上抛。
        """
        if _should_use_direct_summary(
            video=video,
            transcript=transcript,
            context_window_tokens=self._context_window_tokens,
            reserved_output_tokens=self._reserved_output_tokens,
            direct_summary_threshold_ratio=self._direct_summary_threshold_ratio,
        ):
            coro = self._gateway.acomplete_structured(
                [{"role": "user", "content": build_transcript_document_prompt(video, transcript)}],
                response_model=SummaryPayload,
            )
            payload = await cancellable_await(coro, cancellation) if cancellation else await coro
            summary_data = payload.model_dump()
            markdown = render_markdown(summary_data)
            return SummaryDocument(markdown=markdown, summary_data=summary_data)

        chunks = list(enumerate(chunk_segments(transcript.segments), start=1))
        chunk_summaries = await self._summarize_chunks(video, chunks, cancellation)
        coro = self._gateway.acomplete_structured(
            [{"role": "user", "content": build_document_prompt(video, transcript, chunk_summaries)}],
            response_model=SummaryPayload,
        )
        payload = await cancellable_await(coro, cancellation) if cancellation else await coro
        summary_data = payload.model_dump()
        markdown = render_markdown(summary_data)
        return SummaryDocument(markdown=markdown, summary_data=summary_data)

    async def _summarize_chunks(
        self,
        video: VideoAsset,
        chunks: list[tuple[int, list]],
        cancellation: GenerationCancellationContext | None,
    ) -> list[str]:
        """并发地逐分片生成小结，结果按分片序号排序后返回。

        Args:
            video: 视频元信息，传给 `build_chunk_prompt`。
            chunks: `(index, segments)` 元组列表；`index` 用于在提示词中
                标识当前分片编号，并保证最终结果按原顺序还原。
            cancellation: 可选的取消上下文；非 `None` 时在进入协程前先检查
                取消信号，避免白白发起 LLM 调用。

        Returns:
            与输入 `chunks` 等长、按 `index` 升序排列的分片小结文本列表。
        """
        semaphore = asyncio.Semaphore(self._summary_chunk_concurrency)

        async def summarize_chunk(index: int, chunk: list) -> tuple[int, str]:
            """单个分片的小结任务：抢信号量 → 检查取消 → 调 LLM。"""
            async with semaphore:
                if cancellation is not None and cancellation.cancel_requested:
                    from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError
                    raise GenerateCancelledError("任务已取消")
                coro = self._gateway.acomplete_text(
                    [{"role": "user", "content": build_chunk_prompt(video, chunk, index)}]
                )
                summary = await cancellable_await(coro, cancellation) if cancellation else await coro
                return index, summary

        results = await asyncio.gather(
            *(summarize_chunk(index, chunk) for index, chunk in chunks)
        )
        return [summary for _, summary in sorted(results, key=lambda item: item[0])]


def _should_use_direct_summary(
    *,
    video: VideoAsset,
    transcript: Transcript,
    context_window_tokens: int,
    reserved_output_tokens: int,
    direct_summary_threshold_ratio: float,
) -> bool:
    """判定本次总结是否可以直接在一次 LLM 调用中完成。

    判定逻辑：先用 `context_window_tokens - reserved_output_tokens` 算出
    可用于输入的预算，再按 `direct_summary_threshold_ratio` 给出"直接总结"
    的预算上限；只要"直接提示词"的 token 估算不超过该上限就走直接路径。

    Args:
        video: 视频元信息。
        transcript: 转写结果。
        context_window_tokens: 模型上下文窗口大小。
        reserved_output_tokens: 为输出预留的 token 数。
        direct_summary_threshold_ratio: 直接路径占可用输入的比例。

    Returns:
        为 `True` 表示可以走"直接总结"路径；为 `False` 表示需要分片。
    """
    available_tokens = max(1, context_window_tokens - reserved_output_tokens)
    direct_summary_budget = max(1, int(available_tokens * direct_summary_threshold_ratio))
    direct_prompt = build_transcript_document_prompt(video, transcript)
    return _estimate_tokens(direct_prompt) <= direct_summary_budget


def _estimate_tokens(value: str) -> int:
    """粗略估算一段字符串的 token 数。

    采用"UTF-8 字节数 / 3"近似，仅用于在送入 LLM 之前判断是否会超窗口；
    不替代真实的 tokenizer 计数。

    Args:
        value: 待估算的字符串。

    Returns:
        估算的 token 数；空字符串返回 0，非空至少返回 1。
    """
    text = value.strip()
    if not text:
        return 0
    return max(1, len(text.encode("utf-8")) // 3)
