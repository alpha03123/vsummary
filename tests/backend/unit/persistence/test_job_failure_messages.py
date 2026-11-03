"""Configuration gaps reach the user as actionable text, not as「任务参数或目标资源无效」."""

from __future__ import annotations

import pytest

from backend.api.adapters.agent_runtime_provider import LazyAgentRuntimeProvider
from backend.core.errors import UserVisibleError
from backend.video_summary.infrastructure.asr.whisper_cpp_transcriber import WhisperCppTranscriber
from backend.video_summary.infrastructure.persistence.job_worker import _public_failure_detail


class _NoEmbedding:
    def is_downloaded(self, key: str) -> bool:
        return False


def test_missing_whisper_cli_tells_the_user_how_to_get_asr_working(tmp_path):
    with pytest.raises(UserVisibleError) as caught:
        WhisperCppTranscriber(binary_path=str(tmp_path / "missing" / "whisper-cli.exe"), model_path=tmp_path / "model.bin")

    assert "whisper-cli" in _public_failure_detail(caught.value)
    assert "faster-whisper" in _public_failure_detail(caught.value)


def test_index_job_without_the_embedding_model_asks_for_the_download(tmp_path):
    provider = LazyAgentRuntimeProvider(root_dir=tmp_path, workspace=None, session_store=None, rag_model_manager=_NoEmbedding())

    with pytest.raises(UserVisibleError) as caught:
        provider.refresh_workspace_indexes(tmp_path / "index")

    assert "bge-small-zh-v1.5" in _public_failure_detail(caught.value)
