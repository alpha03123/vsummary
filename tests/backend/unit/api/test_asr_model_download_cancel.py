from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.routes.settings import cancel_asr_model_download
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker


class _ModelManager:
    def __init__(self, supported: bool = True) -> None:
        self._supported = supported

    def is_supported(self, model_id: str) -> bool:
        return self._supported and model_id == "large-v3-turbo"


def test_cancel_asr_model_download_marks_provider_scoped_tracker_cancelling() -> None:
    tracker = InMemoryProgressTracker()
    tracker.create_reporter("asr-download/faster_whisper/large-v3-turbo")
    container = SimpleNamespace(
        faster_whisper_model_manager=_ModelManager(),
        model_download_progress_tracker=tracker,
    )

    response = cancel_asr_model_download("faster_whisper", "large-v3-turbo", container)

    snapshot = tracker.get_snapshot("asr-download/faster_whisper/large-v3-turbo")
    assert response == {"status": "cancelling", "task_id": "asr-download/faster_whisper/large-v3-turbo"}
    assert snapshot.status == "cancelling"


def test_cancel_asr_model_download_rejects_unsupported_model() -> None:
    container = SimpleNamespace(
        faster_whisper_model_manager=_ModelManager(supported=False),
        model_download_progress_tracker=InMemoryProgressTracker(),
    )

    with pytest.raises(HTTPException) as error:
        cancel_asr_model_download("faster_whisper", "unknown", container)

    assert error.value.status_code == 400
