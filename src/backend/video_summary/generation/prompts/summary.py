"""视频总结相关的 LLM 提示词与文本辅助函数。

集中维护「单片段总结」「整篇总结」「转写直接总结」三套提示词模板，
以及时间格式化、片段分片、模板渲染等共用工具。提示词模板使用
`string.Template` 占位符，由同模块的 `build_*` 函数负责注入。
"""

from __future__ import annotations

from string import Template

from backend.video_summary.domain.models import Transcript, TranscriptSegment, VideoAsset


# 用于让 LLM 提取单个转写片段章节大纲的提示词。
#
# 输入一段连续转写，输出该片段的主题、要点、术语以及可用于思维
# 导图的两级层级。占位符：`$video_title`、`$chunk_index`、
# `$transcript_text`。对应 `build_chunk_prompt`。
CHUNK_SUMMARY_PROMPT_TEMPLATE = (
    "你正在整理一个中文技术视频的转写片段。\n"
    "视频标题：$video_title\n"
    "这是第 $chunk_index 个片段，请输出中文 Markdown，只保留事实，不要编造。\n"
    "如果片段中存在少量 ASR 噪声或个别句子不完整，忽略噪声并提炼可确认的信息，不要写“后文文本混乱”“文本有误”“内容不清晰”等说明性废话。\n\n"
    "输出格式：\n"
    "## 片段主题\n"
    "- 用 1 句话概括本片段在讲什么\n"
    "## 关键要点\n"
    "- 3 到 6 条要点\n"
    "## 重要术语\n"
    "- 列出术语及简短解释\n"
    "## 可用于思维导图的层级\n"
    "- 一级主题\n"
    "- 二级主题\n\n"
    "转写如下：\n"
    "$transcript_text"
)


# 用于让 LLM 把多个片段总结聚合成结构化总结文档的提示词。
#
# 输入已生成的片段总结列表，输出包含章节、关键结论的结构化 JSON；
# 章节必须给出秒级时间区间。占位符：`$video_title`、`$video_duration`、
# `$transcript_language`、`$chunk_summaries`。对应 `build_document_prompt`。
DOCUMENT_SUMMARY_PROMPT_TEMPLATE = (
    "请基于以下中文视频片段总结，生成结构化 JSON。\n"
    "视频标题：$video_title\n"
    "视频时长：$video_duration\n"
    "识别语言：$transcript_language\n\n"
    "要求：\n"
    "1. 只输出 JSON，不要输出额外解释。\n"
    "2. 不要编造原文没有提到的内容。\n"
    "3. 章节必须给出 start_seconds 和 end_seconds，单位为秒。\n"
    "4. 关键结论控制在 5 到 10 条。\n\n"
    "5. 不要输出对转写质量的评价，不要写“后文文本混乱”“文本识别不完整”这类内容；如果某处信息不足，直接忽略不确定部分，专注总结可确认内容。\n\n"
    "JSON 结构：\n"
    "{\n"
    '  "title": "视频标题",\n'
    '  "one_sentence_summary": "一句话总结",\n'
    '  "core_problem": "视频核心要解决的问题",\n'
    '  "chapters": [\n'
    "    {\n"
    '      "id": "chapter-1",\n'
    '      "title": "章节标题",\n'
    '      "start_seconds": 0,\n'
    '      "end_seconds": 120,\n'
    '      "summary": "章节小结",\n'
    '      "key_points": ["要点1", "要点2"]\n'
    "    }\n"
    "  ],\n"
    '  "key_takeaways": ["结论1", "结论2"]\n'
    "}\n\n"
    "片段总结如下：\n"
    "$chunk_summaries"
)


# 用于让 LLM 直接基于完整转写一次性生成结构化总结文档的提示词。
#
# 与 `DOCUMENT_SUMMARY_PROMPT_TEMPLATE` 的差别是：跳过片段总结聚合步骤，
# 直接由 LLM 在转写全文上完成总结；适合较短的视频。占位符：
# `$video_title`、`$video_duration`、`$transcript_language`、`$transcript_text`。
# 对应 `build_transcript_document_prompt`。
TRANSCRIPT_DOCUMENT_SUMMARY_PROMPT_TEMPLATE = (
    "请基于以下中文视频转写，生成结构化 JSON。\n"
    "视频标题：$video_title\n"
    "视频时长：$video_duration\n"
    "识别语言：$transcript_language\n\n"
    "要求：\n"
    "1. 只输出 JSON，不要输出额外解释。\n"
    "2. 不要编造原文没有提到的内容。\n"
    "3. 章节必须按时间顺序组织，并给出 start_seconds 和 end_seconds，单位为秒。\n"
    "4. 关键结论控制在 5 到 10 条。\n"
    "5. 不要输出对转写质量的评价，不要写“后文文本混乱”“文本识别不完整”这类内容；如果某处信息不足，直接忽略不确定部分，专注总结可确认内容。\n\n"
    "JSON 结构：\n"
    "{\n"
    '  "title": "视频标题",\n'
    '  "one_sentence_summary": "一句话总结",\n'
    '  "core_problem": "视频核心要解决的问题",\n'
    '  "chapters": [\n'
    "    {\n"
    '      "id": "chapter-1",\n'
    '      "title": "章节标题",\n'
    '      "start_seconds": 0,\n'
    '      "end_seconds": 120,\n'
    '      "summary": "章节小结",\n'
    '      "key_points": ["要点1", "要点2"]\n'
    "    }\n"
    "  ],\n"
    '  "key_takeaways": ["结论1", "结论2"]\n'
    "}\n\n"
    "转写如下：\n"
    "$transcript_text"
)


def format_timestamp(seconds: float) -> str:
    """把秒数格式化为 `HH:MM:SS` 或 `MM:SS` 文本。

    负数会被夹到 0；超过一小时时切换到 `HH:MM:SS` 形态。

    Args:
        seconds: 时间长度（秒）。

    Returns:
        格式化后的时间字符串。
    """
    total_seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes:02d}:{remaining_seconds:02d}"


def chunk_segments(segments: list[TranscriptSegment], max_chars: int = 12000) -> list[list[TranscriptSegment]]:
    """把转写片段按字符预算切分成多个分片。

    累计加入片段会让当前分片超过 `max_chars` 时，先把已积累的分片
    提交为一份，再开始新的分片；空文本片段会被跳过；不会把单个
    片段切碎（即使它本身就超过 `max_chars`）。

    Args:
        segments: 按时间顺序排列的转写片段。
        max_chars: 单个分片的字符数预算（含 32 字符/片段的固定开销估算）。

    Returns:
        分片后的转写片段列表；输入为空时返回空列表。
    """
    chunks: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    current_size = 0

    for segment in segments:
        segment_text = segment.text.strip()
        if not segment_text:
            continue
        candidate_size = current_size + len(segment_text) + 32
        if current and candidate_size > max_chars:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(segment)
        current_size += len(segment_text) + 32

    if current:
        chunks.append(current)

    return chunks


def build_chunk_prompt(video: VideoAsset, chunk: list[TranscriptSegment], index: int) -> str:
    """基于「单片段总结」模板构造提示词。

    Args:
        video: 视频资产，用于提供标题。
        chunk: 单个转写分片。
        index: 分片序号（从 1 开始），会作为「第 N 个片段」注入。

    Returns:
        替换好占位符的最终提示词字符串。
    """
    return _render_template(
        CHUNK_SUMMARY_PROMPT_TEMPLATE,
        video_title=video.title,
        chunk_index=str(index),
        transcript_text=segments_to_text(chunk),
    )


def build_document_prompt(
    video: VideoAsset,
    transcript: Transcript,
    chunk_summaries: list[str],
) -> str:
    """基于「整篇总结」模板构造提示词。

    Args:
        video: 视频资产，用于提供标题与时长。
        transcript: 完整转写，用于提供识别语言。
        chunk_summaries: 已生成的各片段总结文本，会用空行连接。

    Returns:
        替换好占位符的最终提示词字符串。
    """
    return _render_template(
        DOCUMENT_SUMMARY_PROMPT_TEMPLATE,
        video_title=video.title,
        video_duration=format_timestamp(video.duration_seconds),
        transcript_language=transcript.language,
        chunk_summaries="\n\n".join(chunk_summaries),
    )


def build_transcript_document_prompt(video: VideoAsset, transcript: Transcript) -> str:
    """基于「转写直接总结」模板构造提示词（跳过片段聚合步骤）。

    Args:
        video: 视频资产，用于提供标题与时长。
        transcript: 完整转写，用于提供语言与全部片段。

    Returns:
        替换好占位符的最终提示词字符串。
    """
    return _render_template(
        TRANSCRIPT_DOCUMENT_SUMMARY_PROMPT_TEMPLATE,
        video_title=video.title,
        video_duration=format_timestamp(video.duration_seconds),
        transcript_language=transcript.language,
        transcript_text=segments_to_text(transcript.segments),
    )


def segments_to_text(segments: list[TranscriptSegment]) -> str:
    """把转写片段序列化为带时间戳前缀的纯文本。

    每行形如 `[HH:MM:SS-HH:MM:SS] 文本`；片段之间用换行分隔。

    Args:
        segments: 转写片段列表。

    Returns:
        可直接注入 LLM 提示词的纯文本。
    """
    lines: list[str] = []
    for segment in segments:
        start = format_timestamp(segment.start_seconds)
        end = format_timestamp(segment.end_seconds)
        lines.append(f"[{start}-{end}] {segment.text}")
    return "\n".join(lines)


def _render_template(template: str, **values: str) -> str:
    """用 `string.Template` 的语法把占位符替换为 `values`。

    Args:
        template: 含 `$name` 风格占位符的模板字符串。
        **values: 占位符名称到字符串的映射。

    Returns:
        替换完毕的字符串。

    Raises:
        KeyError: 模板中存在 `values` 未提供的占位符。
    """
    return Template(template).substitute(values)
