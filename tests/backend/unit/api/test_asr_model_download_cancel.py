from tests._api_fixtures import make_api_container
from unittest.mock import create_autospec

import pytest
from fastapi import HTTPException

from backend.core.context import WorkspaceContext
from backend.local.routes.settings import cancel_asr_model_download
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository
from tests._job_fixtures import job_snapshot


class _ModelManager:
    def __init__(self, supported: bool = True) -> None:
        self._supported = supported

    def is_supported(self, model_id: str) -> bool:
        return self._supported and model_id == "large-v3-turbo"


def test_cancel_asr_model_download_requests_durable_job_cancellation() -> None:
    job_repository = create_autospec(SqlJobRepository, instance=True, spec_set=True)
    job_repository.request_cancel_for_resource.return_value = job_snapshot(
        id="job-1", status="cancelled", resource_type="model", resource_id="asr:faster_whisper:large-v3-turbo",
        operation="prepare_asr_model",
    )
    container = make_api_container(
        faster_whisper_model_manager=_ModelManager(),
        job_repository=job_repository,
    )
    context = WorkspaceContext(workspace_id="workspace-1", actor_id="local-user", request_id="request-1")

    response = cancel_asr_model_download("faster_whisper", "large-v3-turbo", container, context)

    assert response == {"status": "cancelled", "job_id": "job-1"}
    job_repository.request_cancel_for_resource.assert_called_once_with(
        workspace_id="workspace-1", resource_id="asr:faster_whisper:large-v3-turbo", operation="prepare_asr_model",
    )


def test_cancel_asr_model_download_rejects_unsupported_model() -> None:
    container = make_api_container(
        faster_whisper_model_manager=_ModelManager(supported=False),
    )

    with pytest.raises(HTTPException) as error:
        cancel_asr_model_download("faster_whisper", "unknown", container)

    assert error.value.status_code == 400
