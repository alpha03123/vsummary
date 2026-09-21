from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.local.routes.settings import cancel_asr_model_download


class _ModelManager:
    def __init__(self, supported: bool = True) -> None:
        self._supported = supported

    def is_supported(self, model_id: str) -> bool:
        return self._supported and model_id == "large-v3-turbo"


def test_cancel_asr_model_download_requests_durable_job_cancellation() -> None:
    job_repository = SimpleNamespace(
        request_cancel_for_resource=lambda **kwargs: SimpleNamespace(id="job-1", status="cancelled", **kwargs),
    )
    container = SimpleNamespace(
        faster_whisper_model_manager=_ModelManager(),
        sql_workspace=SimpleNamespace(workspace_id="workspace-1"),
        job_repository=job_repository,
    )

    response = cancel_asr_model_download("faster_whisper", "large-v3-turbo", container)

    assert response == {"status": "cancelled", "job_id": "job-1"}


def test_cancel_asr_model_download_rejects_unsupported_model() -> None:
    container = SimpleNamespace(
        faster_whisper_model_manager=_ModelManager(supported=False),
    )

    with pytest.raises(HTTPException) as error:
        cancel_asr_model_download("faster_whisper", "unknown", container)

    assert error.value.status_code == 400
