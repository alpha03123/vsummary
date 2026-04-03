from __future__ import annotations

import json
from pathlib import Path

from backend.video_summary.domain.models import Transcript, TranscriptSegment, VideoAsset
from backend.video_summary.infrastructure.openai_summary import OpenAIResponsesGateway


class OpenAITranscriptEnhancer:
    def __init__(self, model: str, base_url: str, api_key: str) -> None:
        self._gateway = OpenAIResponsesGateway(model=model, base_url=base_url, api_key=api_key)

    def enhance(self, video: VideoAsset, transcript: Transcript, output_dir: Path) -> Transcript:
        chunks = _chunk_segments(transcript.segments)
        enhanced_segments = []
        for index, chunk in enumerate(chunks, start=1):
            corrected_payload = self._gateway.create_text(_build_transcript_enhancement_prompt(video, chunk, index, len(chunks)))
            enhanced_segments.extend(_parse_corrected_segments(corrected_payload, chunk))

        enhanced_transcript = Transcript(
            language=transcript.language,
            segments=enhanced_segments or transcript.segments,
        )
        (output_dir / "transcript.enhanced.json").write_text(
            json.dumps(_build_transcript_payload(enhanced_transcript), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return enhanced_transcript


def _build_transcript_enhancement_prompt(
    video: VideoAsset,
    segments: list[TranscriptSegment],
    index: int,
    total_chunks: int,
) -> str:
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


def _parse_corrected_segments(raw_text: str, fallback_segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    payload = _extract_json_block(raw_text)
    segments = payload.get("segments", [])
    if not isinstance(segments, list):
        raise RuntimeError("Transcript enhancer returned invalid segments payload.")

    normalized_segments = []
    for index, item in enumerate(segments):
        if not isinstance(item, dict):
            continue
        fallback = fallback_segments[min(index, len(fallback_segments) - 1)]
        text = str(item.get("text", fallback.text)).strip() or fallback.text
        normalized_segments.append(
            TranscriptSegment(
                start_seconds=float(item.get("start_seconds", fallback.start_seconds)),
                end_seconds=float(item.get("end_seconds", fallback.end_seconds)),
                text=text,
            )
        )

    if len(normalized_segments) != len(fallback_segments):
        return fallback_segments
    return normalized_segments


def _extract_json_block(raw_text: str) -> dict[str, object]:
    candidate = raw_text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"Model did not return valid JSON: {raw_text[:400]}")
    return json.loads(candidate[start : end + 1])


def _chunk_segments(segments: list[TranscriptSegment], max_chars: int = 10000) -> list[list[TranscriptSegment]]:
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


def _build_transcript_payload(transcript: Transcript) -> dict[str, object]:
    return {
        "language": transcript.language,
        "segments": [
            {
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "text": segment.text,
            }
            for segment in transcript.segments
        ],
    }
