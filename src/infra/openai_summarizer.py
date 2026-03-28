from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from domain.models import SummaryDocument, Transcript, TranscriptSegment, VideoAsset


def format_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes:02d}:{remaining_seconds:02d}"


def _segments_to_text(segments: list[TranscriptSegment]) -> str:
    lines: list[str] = []
    for segment in segments:
        start = format_timestamp(segment.start_seconds)
        end = format_timestamp(segment.end_seconds)
        lines.append(f"[{start}-{end}] {segment.text}")
    return "\n".join(lines)


def _chunk_segments(segments: list[TranscriptSegment], max_chars: int = 12000) -> list[list[TranscriptSegment]]:
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


def _extract_json_block(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"Model did not return valid JSON: {text[:400]}")

    return json.loads(candidate[start : end + 1])


def _normalize_chapter(chapter: dict[str, Any], index: int) -> dict[str, Any]:
    chapter_id = chapter.get("id") or f"chapter-{index + 1}"
    return {
        "id": str(chapter_id),
        "title": str(chapter.get("title", f"章节 {index + 1}")).strip(),
        "start_seconds": float(chapter.get("start_seconds", 0.0) or 0.0),
        "end_seconds": float(chapter.get("end_seconds", 0.0) or 0.0),
        "summary": str(chapter.get("summary", "")).strip(),
        "key_points": [str(item).strip() for item in chapter.get("key_points", []) if str(item).strip()],
    }


def _normalize_mindmap_node(node: dict[str, Any], fallback_id: str) -> dict[str, Any]:
    children = node.get("children", [])
    normalized_children = [
        _normalize_mindmap_node(child, f"{fallback_id}-{index + 1}")
        for index, child in enumerate(children)
        if isinstance(child, dict)
    ]
    return {
        "id": str(node.get("id", fallback_id)),
        "title": str(node.get("title", "")).strip(),
        "summary": str(node.get("summary", "")).strip(),
        "start_seconds": float(node.get("start_seconds", 0.0) or 0.0),
        "end_seconds": float(node.get("end_seconds", 0.0) or 0.0),
        "children": normalized_children,
    }


def _render_markdown(summary_data: dict[str, Any]) -> str:
    lines: list[str] = [f"# {summary_data['title']}", ""]
    lines.append("## 一句话总结")
    lines.append(summary_data["one_sentence_summary"])
    lines.append("")
    lines.append("## 核心问题")
    lines.append(summary_data["core_problem"])
    lines.append("")
    lines.append("## 章节摘要")
    lines.append("")

    for chapter in summary_data["chapters"]:
        start = format_timestamp(chapter["start_seconds"])
        end = format_timestamp(chapter["end_seconds"])
        lines.append(f"### {chapter['title']} ({start} - {end})")
        lines.append(f"<a id=\"{chapter['id']}\"></a>")
        lines.append(chapter["summary"])
        lines.append("")
        if chapter["key_points"]:
            for point in chapter["key_points"]:
                lines.append(f"- {point}")
            lines.append("")

    lines.append("## 关键结论")
    for point in summary_data["key_takeaways"]:
        lines.append(f"- {point}")
    lines.append("")
    lines.append("## 思维导图数据")
    lines.append("交互式思维导图请读取同目录下的 `mindmap.json`。")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


class OpenAIResponsesClient:
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("缺少 OPENAI_API_KEY，无法生成总结。")

        resolved_base_url = (
            base_url
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("OPENAI_API_BASE")
            or "https://api.openai.com/v1/responses"
        )

        self._api_key = api_key
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-5.4")
        self._base_url = resolved_base_url.rstrip("/")

    def summarize(self, video: VideoAsset, transcript: Transcript, output_dir: Path) -> SummaryDocument:
        chunk_summaries: list[str] = []
        for index, chunk in enumerate(_chunk_segments(transcript.segments), start=1):
            chunk_summaries.append(self._summarize_chunk(video, chunk, index))

        summary_data = self._summarize_document(video, transcript, chunk_summaries)
        markdown = _render_markdown(summary_data)

        mindmap_data = summary_data["mindmap"]
        (output_dir / "summary.md").write_text(markdown, encoding="utf-8")
        (output_dir / "summary.json").write_text(
            json.dumps(summary_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "mindmap.json").write_text(
            json.dumps(mindmap_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return SummaryDocument(markdown=markdown, summary_data=summary_data, mindmap_data=mindmap_data)

    def _summarize_chunk(
        self,
        video: VideoAsset,
        chunk: list[TranscriptSegment],
        index: int,
    ) -> str:
        prompt = (
            f"你正在整理一个中文技术视频的转写片段。\n"
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
            f"{_segments_to_text(chunk)}"
        )
        return self._create_text(prompt)

    def _summarize_document(
        self,
        video: VideoAsset,
        transcript: Transcript,
        chunk_summaries: list[str],
    ) -> dict[str, Any]:
        joined_summaries = "\n\n".join(chunk_summaries)
        prompt = (
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
        raw_payload = self._create_text(prompt)
        parsed = _extract_json_block(raw_payload)

        chapters = [
            _normalize_chapter(chapter, index)
            for index, chapter in enumerate(parsed.get("chapters", []))
            if isinstance(chapter, dict)
        ]
        key_takeaways = [
            str(item).strip() for item in parsed.get("key_takeaways", []) if str(item).strip()
        ]
        mindmap = _normalize_mindmap_node(
            parsed.get("mindmap", {"title": video.title, "children": []}),
            "root",
        )

        return {
            "title": str(parsed.get("title", video.title)).strip(),
            "one_sentence_summary": str(parsed.get("one_sentence_summary", "")).strip(),
            "core_problem": str(parsed.get("core_problem", "")).strip(),
            "chapters": chapters,
            "key_takeaways": key_takeaways,
            "mindmap": mindmap,
        }

    def _create_text(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "input": prompt,
            "text": {"format": {"type": "text"}},
        }
        request = urllib.request.Request(
            self._base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI 请求失败: {error.code} {body}") from error

        output_text = raw_response.get("output_text")
        if output_text:
            return output_text.strip()

        output_items = raw_response.get("output", [])
        content_parts: list[str] = []
        for item in output_items:
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    content_parts.append(content["text"].strip())
        if content_parts:
            return "\n".join(part for part in content_parts if part)

        raise RuntimeError(f"OpenAI 返回中缺少 output_text: {raw_response}")
