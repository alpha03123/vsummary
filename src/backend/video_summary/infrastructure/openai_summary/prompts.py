from __future__ import annotations

from backend.video_summary.domain.models import Transcript, TranscriptSegment, VideoAsset


def format_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes:02d}:{remaining_seconds:02d}"


def chunk_segments(segments: list[TranscriptSegment], max_chars: int = 12000) -> list[list[TranscriptSegment]]:
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
    return (
        "你正在整理一个中文技术视频的转写片段。\n"
        f"视频标题：{video.title}\n"
        f"这是第 {index} 个片段，请输出中文 Markdown，只保留事实，不要编造。\n\n"
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
        f"{segments_to_text(chunk)}"
    )


def build_document_prompt(
    video: VideoAsset,
    transcript: Transcript,
    chunk_summaries: list[str],
) -> str:
    joined_summaries = "\n\n".join(chunk_summaries)
    return (
        "请基于以下中文视频片段总结，生成结构化 JSON。\n"
        f"视频标题：{video.title}\n"
        f"视频时长：{format_timestamp(video.duration_seconds)}\n"
        f"识别语言：{transcript.language}\n\n"
        "要求：\n"
        "1. 只输出 JSON，不要输出额外解释。\n"
        "2. 不要编造原文没有提到的内容。\n"
        "3. 章节必须给出 start_seconds 和 end_seconds，单位为秒。\n"
        "4. 思维导图必须是可递归展开的树结构。\n"
        "5. 关键结论控制在 5 到 10 条。\n\n"
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
        '  "key_takeaways": ["结论1", "结论2"],\n'
        '  "mindmap": {\n'
        '    "id": "root",\n'
        '    "title": "根节点标题",\n'
        '    "summary": "根节点摘要",\n'
        '    "start_seconds": 0,\n'
        f'    "end_seconds": {int(video.duration_seconds)},\n'
        '    "children": [\n'
        "      {\n"
        '        "id": "node-1",\n'
        '        "title": "一级节点",\n'
        '        "summary": "节点摘要",\n'
        '        "start_seconds": 30,\n'
        '        "end_seconds": 200,\n'
        '        "children": []\n'
        "      }\n"
        "    ]\n"
        "  }\n"
        "}\n\n"
        "片段总结如下：\n"
        f"{joined_summaries}"
    )


def segments_to_text(segments: list[TranscriptSegment]) -> str:
    lines: list[str] = []
    for segment in segments:
        start = format_timestamp(segment.start_seconds)
        end = format_timestamp(segment.end_seconds)
        lines.append(f"[{start}-{end}] {segment.text}")
    return "\n".join(lines)

