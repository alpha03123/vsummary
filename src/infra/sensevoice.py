from __future__ import annotations

import json
from pathlib import Path

from domain.models import Transcript, TranscriptSegment


class SenseVoiceTranscriber:
    def __init__(self, model_id: str, device: str = "cuda:0") -> None:
        try:
            from funasr import AutoModel
        except ImportError as error:
            raise RuntimeError("SenseVoice requires funasr. Install dependencies first.") from error

        self._model_id = model_id
        self._device = device
        self._model = AutoModel(
            model=model_id,
            trust_remote_code=True,
            device=device,
        )

    def transcribe(self, audio_path: Path, output_stem: Path) -> Transcript:
        output_stem.parent.mkdir(parents=True, exist_ok=True)
        result = self._model.generate(
            input=str(audio_path),
            language="zh",
            use_itn=True,
            batch_size_s=300,
        )

        payload = result[0] if isinstance(result, list) else result
        text = _extract_text(payload).strip()
        segments = _extract_segments(payload, fallback_text=text)

        debug_path = output_stem.with_suffix(".sensevoice.json")
        debug_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return Transcript(language="zh", segments=segments)


def _extract_text(payload: dict) -> str:
    if isinstance(payload, dict):
        if isinstance(payload.get("text"), str):
            return payload["text"]
        if isinstance(payload.get("text"), list):
            return "\n".join(str(item) for item in payload["text"])
    return ""


def _extract_segments(payload: dict, fallback_text: str) -> list[TranscriptSegment]:
    if isinstance(payload, dict):
        if isinstance(payload.get("sentence_info"), list):
            segments: list[TranscriptSegment] = []
            for item in payload["sentence_info"]:
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                segments.append(
                    TranscriptSegment(
                        start_seconds=float(item.get("start", 0.0)) / 1000.0,
                        end_seconds=float(item.get("end", 0.0)) / 1000.0,
                        text=text,
                    )
                )
            if segments:
                return segments

    if fallback_text:
        return [TranscriptSegment(start_seconds=0.0, end_seconds=0.0, text=fallback_text)]
    return []
