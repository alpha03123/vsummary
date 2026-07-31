from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.video_summary.generation.cancellation import GenerationCancellationContext
from backend.video_summary.infrastructure.subtitle_transcripts import SubtitleTranscriptProvider


_SRT = """1
00:00:00,000 --> 00:00:01,500
简体中文字幕

"""


def test_bilibili_ai_zh_subtitle_is_selected(monkeypatch, tmp_path: Path) -> None:
    class FakeYoutubeDL:
        def __init__(self, options: dict[str, object]) -> None:
            assert options["listsubtitles"] is True

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool) -> dict[str, object]:
            assert "BV1vJ3P6KEkh" in url
            return {
                "subtitles": {
                    "ai-en": [{"ext": "srt", "data": _SRT.replace("简体中文", "English")}],
                    "ai-zh": [{"ext": "srt", "data": _SRT}],
                }
            }

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(
        "backend.video_summary.infrastructure.subtitle_transcripts._load_embedded_subtitle",
        lambda video_path, output_path, cancellation=None: None,
    )
    transcript = SubtitleTranscriptProvider().load(tmp_path / "BV1vJ3P6KEkh.mp4", tmp_path)

    assert transcript is not None
    assert transcript.language == "zh"
    assert transcript.full_text == "简体中文字幕"


def test_bilibili_non_chinese_subtitles_are_rejected(monkeypatch, tmp_path: Path) -> None:
    class FakeYoutubeDL:
        def __init__(self, options: dict[str, object]) -> None:
            pass

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool) -> dict[str, object]:
            return {"subtitles": {"ai-en": [{"ext": "srt", "data": _SRT}]}}

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(
        "backend.video_summary.infrastructure.subtitle_transcripts._load_embedded_subtitle",
        lambda video_path, output_path, cancellation=None: None,
    )
    transcript = SubtitleTranscriptProvider().load(tmp_path / "BV1NoTk6SERz.mp4", tmp_path)

    assert transcript is None


def test_embedded_chinese_text_subtitle_is_exported(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], cancellation=None) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                '{"streams":[{"index":2,"codec_type":"subtitle","codec_name":"mov_text","tags":{"language":"zh-Hans"}}]}',
                "",
            )
        Path(command[-1]).write_text(_SRT, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("backend.video_summary.infrastructure.subtitle_transcripts._run_subprocess", fake_run)
    transcript = SubtitleTranscriptProvider().load(tmp_path / "local.mp4", tmp_path)

    assert transcript is not None
    assert transcript.full_text == "简体中文字幕"
    assert calls[1][calls[1].index("-map") + 1] == "0:2"


def test_embedded_non_chinese_subtitle_is_rejected(monkeypatch, tmp_path: Path) -> None:
    def fake_run(command: list[str], cancellation=None) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            '{"streams":[{"index":2,"codec_type":"subtitle","codec_name":"mov_text","tags":{"language":"en"}}]}',
            "",
        )

    monkeypatch.setattr("backend.video_summary.infrastructure.subtitle_transcripts._run_subprocess", fake_run)
    assert SubtitleTranscriptProvider().load(tmp_path / "local.mp4", tmp_path) is None


def test_embedded_subtitle_subprocess_is_cancelled(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = -9
            self.killed = False

        def kill(self) -> None:
            self.killed = True

        def communicate(self) -> tuple[str, str]:
            cancellation.request_cancel()
            return "", ""

    cancellation = GenerationCancellationContext("subtitle-test")
    process = FakeProcess()

    monkeypatch.setattr(
        "backend.video_summary.infrastructure.subtitle_transcripts.subprocess.Popen",
        lambda *args, **kwargs: process,
    )

    from backend.video_summary.infrastructure.subtitle_transcripts import _run_subprocess

    with pytest.raises(InterruptedError):
        _run_subprocess(["ffprobe", "-version"], cancellation)

    assert process.killed is True
