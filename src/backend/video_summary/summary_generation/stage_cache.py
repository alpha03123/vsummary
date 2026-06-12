from __future__ import annotations

import json
import os
import shutil
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from backend.common.filesystem import atomic_write_text
from backend.video_summary.summary_generation.models import Transcript, TranscriptSegment


class GenerationStageCache:
    _VERSION = 1

    def __init__(self, cache_dir: Path, video_path: Path) -> None:
        self._cache_dir = cache_dir
        self._video_path = video_path

    def restore_audio(self, target_path: Path, *, identity: str) -> bool:
        source_path = self._cache_dir / "media" / "audio.wav"
        if not self._is_valid("media", identity=identity):
            return False
        if not source_path.exists():
            return False
        _copy_file_atomic(source_path, target_path)
        return True

    def store_audio(self, source_path: Path, *, identity: str) -> None:
        target_path = self._cache_dir / "media" / "audio.wav"
        _copy_file_atomic(source_path, target_path)
        self._write_manifest("media", identity=identity)

    def load_transcript(self, stage: str, *, identity: str) -> Transcript | None:
        if not self._is_valid(stage, identity=identity):
            return None
        transcript_path = self._transcript_path(stage)
        if not transcript_path.exists():
            return None
        return _transcript_from_payload(json.loads(transcript_path.read_text(encoding="utf-8")))

    def store_transcript(self, stage: str, transcript: Transcript, *, identity: str) -> None:
        payload = _transcript_to_payload(transcript)
        atomic_write_text(
            self._transcript_path(stage),
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        self._write_manifest(stage, identity=identity)

    def _transcript_path(self, stage: str) -> Path:
        if stage == "whisper":
            file_name = "transcript.raw.json"
        elif stage == "transcript-enhance":
            file_name = "transcript.enhanced.json"
        else:
            raise ValueError(f"Unsupported transcript cache stage: {stage}")
        return self._cache_dir / stage / file_name

    def _is_valid(self, stage: str, *, identity: str) -> bool:
        manifest_path = self._manifest_path(stage)
        if not manifest_path.exists():
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest == {
            "version": self._VERSION,
            "stage": stage,
            "identity": identity,
            "video_fingerprint": self._video_fingerprint(),
        }

    def _write_manifest(self, stage: str, *, identity: str) -> None:
        payload = {
            "version": self._VERSION,
            "stage": stage,
            "identity": identity,
            "video_fingerprint": self._video_fingerprint(),
        }
        atomic_write_text(
            self._manifest_path(stage),
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _manifest_path(self, stage: str) -> Path:
        return self._cache_dir / stage / "manifest.json"

    def _video_fingerprint(self) -> str:
        stat = self._video_path.stat()
        digest = sha256()
        digest.update(str(self._video_path.resolve()).encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        return digest.hexdigest()


def _copy_file_atomic(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f".{target_path.name}.{uuid4().hex}.tmp")
    try:
        shutil.copyfile(source_path, temp_path)
        os.replace(temp_path, target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _transcript_to_payload(transcript: Transcript) -> dict[str, object]:
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


def _transcript_from_payload(payload: dict[str, object]) -> Transcript:
    segments_payload = payload["segments"]
    if not isinstance(segments_payload, list):
        raise ValueError("Invalid cached transcript: segments must be a list")
    segments: list[TranscriptSegment] = []
    for segment in segments_payload:
        if not isinstance(segment, dict):
            raise ValueError("Invalid cached transcript: segment must be an object")
        segments.append(
            TranscriptSegment(
                start_seconds=float(segment["start_seconds"]),
                end_seconds=float(segment["end_seconds"]),
                text=str(segment["text"]),
            )
        )
    return Transcript(
        language=str(payload["language"]),
        segments=segments,
    )
