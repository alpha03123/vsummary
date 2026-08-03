from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
import sys
import types

import pytest

from backend.video_summary.infrastructure.asr.aliyun_bailian_transcriber import (
    AliyunBailianTranscriber,
)


class _Response:
    def __init__(self, *, output: dict[str, object], status_code: int = HTTPStatus.OK) -> None:
        self.status_code = status_code
        self.output = output
        self.code = ""
        self.message = ""


class _HttpResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "transcripts": [
                {
                    "sentences": [
                        {"begin_time": 1000, "end_time": 2500, "text": " 第一段 "},
                        {"begin_time": 2500, "end_time": 4000, "text": "第二段"},
                    ]
                }
            ]
        }


class _HttpClient:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def get(self, url: str) -> _HttpResponse:
        assert url == "https://example.test/transcript.json"
        return _HttpResponse()


def test_aliyun_bailian_transcriber_uploads_audio_and_maps_sentences(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, object]] = []

    class OssUtils:
        @classmethod
        def upload(cls, *, model, file_path, api_key, base_address):
            calls.append(("upload", (model, Path(file_path).name, api_key, base_address)))
            return "oss://dashscope-instant/audio.wav", {"upload_dir": "dashscope-instant"}

    class Transcription:
        @classmethod
        def async_call(cls, *, model, file_urls, api_key, base_address, headers, language_hints=None):
            calls.append(("async_call", (model, file_urls, api_key, base_address, headers, language_hints)))
            return _Response(output={"task_id": "task-1", "task_status": "PENDING"})

        @classmethod
        def wait(cls, task, *, api_key, base_address):
            calls.append(("wait", (task.output["task_id"], api_key, base_address)))
            return _Response(
                output={
                    "task_id": "task-1",
                    "task_status": "SUCCEEDED",
                    "results": [{"transcription_url": "https://example.test/transcript.json"}],
                }
            )

    dashscope_module = types.ModuleType("dashscope")
    audio_module = types.ModuleType("dashscope.audio")
    asr_module = types.ModuleType("dashscope.audio.asr")
    asr_module.Transcription = Transcription
    utils_module = types.ModuleType("dashscope.utils")
    oss_utils_module = types.ModuleType("dashscope.utils.oss_utils")
    oss_utils_module.OssUtils = OssUtils
    monkeypatch.setitem(sys.modules, "dashscope", dashscope_module)
    monkeypatch.setitem(sys.modules, "dashscope.audio", audio_module)
    monkeypatch.setitem(sys.modules, "dashscope.audio.asr", asr_module)
    monkeypatch.setitem(sys.modules, "dashscope.utils", utils_module)
    monkeypatch.setitem(sys.modules, "dashscope.utils.oss_utils", oss_utils_module)

    monkeypatch.setattr(
        "backend.video_summary.infrastructure.asr.aliyun_bailian_transcriber.httpx.Client",
        _HttpClient,
    )

    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    progress: list[float] = []
    transcriber = AliyunBailianTranscriber(
        model="paraformer-v2",
        base_url="https://dashscope.aliyuncs.com",
        api_key="dashscope-key",
        language="zh",
    )

    transcript = transcriber.transcribe(audio_path, tmp_path / "transcript", progress.append)

    assert [segment.text for segment in transcript.segments] == ["第一段", "第二段"]
    assert transcript.segments[0].start_seconds == 1.0
    assert transcript.segments[0].end_seconds == 2.5
    assert progress[-1] == 1.0
    assert calls[0] == (
        "upload",
        ("paraformer-v2", "audio.wav", "dashscope-key", "https://dashscope.aliyuncs.com/api/v1"),
    )
    assert calls[1] == (
        "async_call",
        (
            "paraformer-v2",
            ["oss://dashscope-instant/audio.wav"],
            "dashscope-key",
            "https://dashscope.aliyuncs.com/api/v1",
            {"X-DashScope-OssResourceResolve": "enable"},
            ["zh"],
        ),
    )


def test_aliyun_bailian_transcriber_omits_language_hints_for_auto(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class Transcription:
        @classmethod
        def async_call(cls, **kwargs):
            calls.append(kwargs)
            return _Response(output={"task_id": "task-1", "task_status": "PENDING"})

    asr_module = types.ModuleType("dashscope.audio.asr")
    asr_module.Transcription = Transcription
    monkeypatch.setitem(sys.modules, "dashscope.audio.asr", asr_module)

    transcriber = AliyunBailianTranscriber(
        model="paraformer-v2",
        base_url="https://dashscope.aliyuncs.com",
        api_key="dashscope-key",
        language="auto",
    )
    transcriber._submit_transcription("oss://dashscope-instant/audio.wav")

    assert "language_hints" not in calls[0]


def test_aliyun_bailian_transcriber_no_valid_fragment_returns_placeholder(monkeypatch, tmp_path: Path, caplog) -> None:
    class Transcription:
        @classmethod
        def async_call(cls, *, model, file_urls, api_key, base_address, headers, language_hints=None):
            return _Response(output={"task_id": "task-1", "task_status": "PENDING"})

        @classmethod
        def wait(cls, task, *, api_key, base_address):
            return _Response(
                output={
                    "task_id": "task-1",
                    "task_status": "FAILED",
                    "results": [
                        {
                            "subtask_status": "FAILED",
                            "code": "SUCCESS_WITH_NO_VALID_FRAGMENT",
                            "message": "SUCCESS_WITH_NO_VALID_FRAGMENT",
                        }
                    ],
                }
            )

    class OssUtils:
        @classmethod
        def upload(cls, *, model, file_path, api_key, base_address):
            return "oss://dashscope-instant/audio.wav", {"upload_dir": "dashscope-instant"}

    asr_module = types.ModuleType("dashscope.audio.asr")
    asr_module.Transcription = Transcription
    oss_utils_module = types.ModuleType("dashscope.utils.oss_utils")
    oss_utils_module.OssUtils = OssUtils
    monkeypatch.setitem(sys.modules, "dashscope.audio.asr", asr_module)
    monkeypatch.setitem(sys.modules, "dashscope.utils.oss_utils", oss_utils_module)

    transcriber = AliyunBailianTranscriber(
        model="paraformer-v2",
        base_url="https://dashscope.aliyuncs.com",
        api_key="dashscope-key",
    )

    caplog.set_level("ERROR")

    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    transcript = transcriber.transcribe(audio_path, tmp_path / "transcript")

    assert [segment.text for segment in transcript.segments] == ["无明显人声"]
    assert "阿里云百炼转写任务未成功：FAILED" in caplog.text
    assert "task_id=task-1" in caplog.text
    assert "code=SUCCESS_WITH_NO_VALID_FRAGMENT" in caplog.text
    assert "message=SUCCESS_WITH_NO_VALID_FRAGMENT" in caplog.text
