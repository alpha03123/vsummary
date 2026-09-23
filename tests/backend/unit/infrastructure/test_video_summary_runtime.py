from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.video_summary.infrastructure.video_summary_runtime import AsrModelNotReadyError, build_video_summary_runtime


def test_missing_faster_whisper_model_is_deferred_until_asr_is_needed(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        asr=SimpleNamespace(
            provider="faster_whisper",
            language="auto",
            faster_whisper=SimpleNamespace(
                models_dir=tmp_path / "models",
                model_size="small",
                device="cpu",
                compute_type="int8",
                transcription_mode="fast",
                initial_prompt="",
            ),
        ),
        openai=SimpleNamespace(provider="openai", model="test", base_url="http://127.0.0.1:1", api_key="test"),
        agent_context=SimpleNamespace(
            reasoning_effort="none",
            window_tokens=8_192,
            reserved_output_tokens=512,
            direct_summary_threshold_ratio=0.9,
        ),
        generation=SimpleNamespace(summary_chunk_concurrency=1),
    )

    runtime = build_video_summary_runtime(settings)

    with pytest.raises(AsrModelNotReadyError, match="尚未下载"):
        runtime.transcriber.transcribe(tmp_path / "audio.wav", tmp_path / "transcript")
