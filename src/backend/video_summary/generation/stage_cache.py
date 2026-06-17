"""生成阶段产物缓存。

按「stage」（media/whisper/transcript-enhance）分别落盘中间产物，
并通过 manifest 记录版本号、阶段名、实现身份与视频指纹，使下次
启动同视频生成时能够直接复用——跳过最耗时的音频抽取与转写步骤。

失效规则：manifest 任一字段不匹配（版本升级、实现身份变更、视频
文件被替换）即视为缓存失效；任何字段改动都需要重新跑该阶段。
"""

from __future__ import annotations

import json
import os
import shutil
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from backend.shared.filesystem import atomic_write_text
from backend.video_summary.domain.models import Transcript, TranscriptSegment


class GenerationStageCache:
    """按阶段缓存视频生成中间产物。

    Attributes:
        _VERSION: manifest 的格式版本号；任何字段调整都要 +1 以便
            自动让旧缓存失效。
    """

    _VERSION = 1

    def __init__(self, cache_dir: Path, video_path: Path) -> None:
        """注入缓存根目录与目标视频路径；视频路径用于生成指纹。"""
        self._cache_dir = cache_dir
        self._video_path = video_path

    def restore_audio(self, target_path: Path, *, identity: str) -> bool:
        """把缓存中的 `media/audio.wav` 拷贝到 `target_path`。

        拷贝使用「临时文件 + os.replace」原子写入，确保目标路径在
        拷贝过程中不会被读到半截文件。

        Args:
            target_path: 调用方期望的音频文件落地路径。
            identity: 媒体处理器实现身份（用于校验缓存有效性）。

        Returns:
            若缓存有效且拷贝成功则为 `True`；否则为 `False`，调用方
            应回退到重新抽取音频。
        """
        source_path = self._cache_dir / "media" / "audio.wav"
        if not self._is_valid("media", identity=identity):
            return False
        if not source_path.exists():
            return False
        _copy_file_atomic(source_path, target_path)
        return True

    def store_audio(self, source_path: Path, *, identity: str) -> None:
        """把音频文件存到缓存并刷新 `media` 阶段的 manifest。

        Args:
            source_path: 已抽取完毕的音频文件路径。
            identity: 媒体处理器实现身份。
        """
        target_path = self._cache_dir / "media" / "audio.wav"
        _copy_file_atomic(source_path, target_path)
        self._write_manifest("media", identity=identity)

    def load_transcript(self, stage: str, *, identity: str) -> Transcript | None:
        """读取某阶段的转写缓存。

        Args:
            stage: 转写阶段名，目前支持 `whisper` 与 `transcript-enhance`。
            identity: 对应阶段的实现身份（whisper 模型或增强器）。

        Returns:
            缓存命中时返回 `Transcript`；缓存缺失或失效时返回 `None`。
        """
        if not self._is_valid(stage, identity=identity):
            return None
        transcript_path = self._transcript_path(stage)
        if not transcript_path.exists():
            return None
        return _transcript_from_payload(json.loads(transcript_path.read_text(encoding="utf-8")))

    def store_transcript(self, stage: str, transcript: Transcript, *, identity: str) -> None:
        """把转写结果写入缓存并刷新对应阶段的 manifest。"""
        payload = _transcript_to_payload(transcript)
        atomic_write_text(
            self._transcript_path(stage),
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        self._write_manifest(stage, identity=identity)

    def _transcript_path(self, stage: str) -> Path:
        """根据阶段名返回对应的转写 JSON 路径；未知阶段会抛 `ValueError`。"""
        if stage == "whisper":
            file_name = "transcript.raw.json"
        elif stage == "transcript-enhance":
            file_name = "transcript.enhanced.json"
        else:
            raise ValueError(f"Unsupported transcript cache stage: {stage}")
        return self._cache_dir / stage / file_name

    def _is_valid(self, stage: str, *, identity: str) -> bool:
        """校验某阶段的 manifest 是否仍有效（版本/身份/视频指纹全部匹配）。"""
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
        """写出当前阶段的 manifest 快照。"""
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
        """返回某阶段 manifest 的存储路径。"""
        return self._cache_dir / stage / "manifest.json"

    def _video_fingerprint(self) -> str:
        """根据视频绝对路径、大小与 mtime 计算指纹。

        任一项变化都会使整组缓存失效，确保用户替换视频文件后不会
        误读到旧数据。
        """
        stat = self._video_path.stat()
        digest = sha256()
        digest.update(str(self._video_path.resolve()).encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        return digest.hexdigest()


def _copy_file_atomic(source_path: Path, target_path: Path) -> None:
    """以「临时文件 + os.replace」方式原子拷贝文件。"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f".{target_path.name}.{uuid4().hex}.tmp")
    try:
        shutil.copyfile(source_path, temp_path)
        os.replace(temp_path, target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _transcript_to_payload(transcript: Transcript) -> dict[str, object]:
    """把 `Transcript` 序列化为可写入 JSON 的字典。"""
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
    """从 JSON 字典反序列化为 `Transcript`；结构不符时抛 `ValueError`。"""
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
