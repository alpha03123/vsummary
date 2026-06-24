"""基于 LiteLLM 的转写增强适配器。

按"修正 ASR 噪声 + 严禁虚构事实"的规则，把 faster-whisper 输出的原始转写
分块送入 LLM 进行纠错与补全，并保留原始时间戳。
"""

from __future__ import annotations

import json

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.domain.models import Transcript, TranscriptSegment, VideoAsset
from backend.video_summary.generation import TranscriptEnhancementPayload
from backend.video_summary.generation.cancellation import GenerationCancellationContext, cancellable_await


class LiteLLMTranscriptEnhancer:
    """通过 LiteLLM 异步调用 LLM 修正转写文本的实现。

    业务场景：在"转写增强"开关开启时，本适配器串行地按分块把原始转写喂给
    LLM，让其修正 ASR 噪声、补全标点，同时严格保留原始时间戳与语言。

    实现要点：
    - 提示词构造：固定中文 prompt 模板 + 视频标题 + 分块进度 + JSON 形式的
      待纠正段落，由 `_build_transcript_enhancement_prompt` 渲染；
    - 输出约束：使用 `TranscriptEnhancementPayload` Pydantic schema 强制
      LLM 输出结构，时间戳会被强制转 `float`；
    - 错误处理：若 LLM 返回的分片数与输入不一致，整体退回原始分片；
      若文本为空，回退到对应原始文本；不抛错到调用方；
    - 取消传播：每个分块前先检查 `cancellation.cancel_requested`，LLM 调用
      也用 `cancellable_await` 包装，取消时抛 `GenerateCancelledError`；
    - 缓存身份：`cache_identity` 由类模块路径 + 类限定名 + 网关身份拼接，
      便于上游按"实现 + 网关"维度复用 LLM 响应缓存。
    """

    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        """注入 LiteLLM 网关实例并构造缓存身份字符串。

        Args:
            gateway: 提供 `acomplete_structured` 能力的 LLM 网关。
        """
        self._gateway = gateway
        gateway_identity = getattr(gateway, "cache_identity", type(gateway).__qualname__)
        self.cache_identity = "|".join([type(self).__module__, type(self).__qualname__, str(gateway_identity)])

    async def enhance(
        self,
        video: VideoAsset,
        transcript: Transcript,
        cancellation: GenerationCancellationContext | None = None,
    ) -> Transcript:
        """对一份转写逐分块调用 LLM 完成 ASR 噪声修正。

        Args:
            video: 视频元信息，用于提示词中的标题。
            transcript: 原始转写文本。
            cancellation: 可选的取消上下文；非 `None` 时在每个分块前检查
                取消信号，并使用 `cancellable_await` 包装 LLM 调用。

        Returns:
            增强后的 `Transcript`，沿用原始 `language`；若所有分块都被 LLM
            清空则退回原始 `segments`，避免输出空转写。

        Raises:
            GenerateCancelledError: 取消信号触发时抛出。
        """
        chunks = _chunk_segments(transcript.segments)
        enhanced_segments = []
        for index, chunk in enumerate(chunks, start=1):
            if cancellation is not None and cancellation.cancel_requested:
                from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError
                raise GenerateCancelledError("任务已取消")
            coro = self._gateway.acomplete_structured(
                [{"role": "user", "content": _build_transcript_enhancement_prompt(video, chunk, index, len(chunks))}],
                response_model=TranscriptEnhancementPayload,
            )
            if cancellation is not None:
                corrected_payload = await cancellable_await(coro, cancellation)
            else:
                corrected_payload = await coro
            enhanced_segments.extend(_parse_corrected_segments(corrected_payload, chunk))

        return Transcript(
            language=transcript.language,
            segments=enhanced_segments or transcript.segments,
        )


def _build_transcript_enhancement_prompt(
    video: VideoAsset,
    segments: list[TranscriptSegment],
    index: int,
    total_chunks: int,
) -> str:
    """渲染转写增强的中文提示词。

    Args:
        video: 视频元信息。
        segments: 当前分块内的转写段落。
        index: 当前分块序号（从 1 开始）。
        total_chunks: 分块总数。

    Returns:
        渲染完成的提示词字符串（含任务要求与待纠正 JSON）。
    """
    return (
        "你正在纠正中文视频转写文本。\n"
        f"视频标题：{video.title}\n"
        f"当前片段块：{index}/{total_chunks}\n\n"
        "任务要求：\n"
        "1. 只修正明显的 ASR 错字、断句问题、标点问题、同音误识别。\n"
        "2. 严禁凭空补充视频里没说过的事实。\n"
        "3. 如果原句存在少量噪声或含糊片段，保留可确认部分，不要写“后文文本混乱”“内容无法识别”等评价性描述。\n"
        "4. 必须保留每条 segment 的 start_seconds 和 end_seconds。\n"
        "5. 输出 JSON，格式如下：\n"
        "{\n"
        '  "segments": [\n'
        "    {\n"
        '      "start_seconds": 0.0,\n'
        '      "end_seconds": 3.2,\n'
        '      "text": "纠正后的文本"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "待纠正转写：\n"
        f"{_segments_to_json(segments)}"
    )


def _parse_corrected_segments(
    payload: TranscriptEnhancementPayload,
    fallback_segments: list[TranscriptSegment],
) -> list[TranscriptSegment]:
    """把 LLM 返回的分段纠正结果规整为 `TranscriptSegment` 列表。

    规整策略：
    - 文本：去空白；若 LLM 给空文本则回退到原始 `text`；
    - 时间戳：强制转 `float`；
    - 数量校验：若返回数量与输入不一致，整体退回到原始分段（避免引入空段
      或漏段）。

    Args:
        payload: LLM 返回的结构化纠正结果。
        fallback_segments: 当前分块的原始分段列表，用于回退与缺位填充。

    Returns:
        规整后的 `TranscriptSegment` 列表。
    """
    segments = payload.segments
    normalized_segments = []
    for index, item in enumerate(segments):
        fallback = fallback_segments[min(index, len(fallback_segments) - 1)]
        text = item.text.strip() or fallback.text
        normalized_segments.append(
            TranscriptSegment(
                start_seconds=float(item.start_seconds),
                end_seconds=float(item.end_seconds),
                text=text,
            )
        )

    if len(normalized_segments) != len(fallback_segments):
        return fallback_segments
    return normalized_segments


def _chunk_segments(segments: list[TranscriptSegment], max_chars: int = 10000) -> list[list[TranscriptSegment]]:
    """按字符上限把转写段落切成多个分块。

    算法：累加段落文本长度（每段预留 64 字符的元数据/分隔开销），超过上限
    时闭合当前块并开新块；空文本段落直接跳过。

    Args:
        segments: 原始转写段落列表。
        max_chars: 单个分块的近似字符数上限，默认 10000。

    Returns:
        分块后的分段列表，每个子列表是若干连续的 `TranscriptSegment`。
    """
    chunks: list[list[TranscriptSegment]] = []
    current_chunk: list[TranscriptSegment] = []
    current_size = 0

    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        candidate_size = current_size + len(text) + 64
        if current_chunk and candidate_size > max_chars:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0
        current_chunk.append(segment)
        current_size += len(text) + 64

    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def _segments_to_json(segments: list[TranscriptSegment]) -> str:
    """把一组转写段落序列化为供 LLM 阅读的 JSON 字符串。

    Args:
        segments: 待序列化的转写段落列表。

    Returns:
        形如 `{"segments": [...]}` 的 JSON 文本，使用 `ensure_ascii=False`
        保留中文。
    """
    return json.dumps(
        {
            "segments": [
                {
                    "start_seconds": segment.start_seconds,
                    "end_seconds": segment.end_seconds,
                    "text": segment.text,
                }
                for segment in segments
            ]
        },
        ensure_ascii=False,
        indent=2,
    )
