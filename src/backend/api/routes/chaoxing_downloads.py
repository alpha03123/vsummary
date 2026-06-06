from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.api.container import ApiContainerDep
from backend.api.contracts import ChaoxingChromiumResponse
from backend.api.sse import stream_progress_events

router = APIRouter()


@router.get("/api/linked/chaoxing/chromium", response_model=ChaoxingChromiumResponse)
def get_chaoxing_chromium(container: ApiContainerDep) -> ChaoxingChromiumResponse:
    return _to_chaoxing_chromium_response(container.chaoxing_chromium_manager.get_status())


@router.post("/api/linked/chaoxing/chromium/download", response_model=ChaoxingChromiumResponse)
def download_chaoxing_chromium(container: ApiContainerDep) -> ChaoxingChromiumResponse:
    return _to_chaoxing_chromium_response(container.chaoxing_chromium_manager.start_download())


@router.get("/api/linked/chaoxing/chromium/download/progress")
async def stream_chaoxing_chromium_download_progress(container: ApiContainerDep) -> StreamingResponse:
    return StreamingResponse(
        stream_progress_events(
            tracker=container.chaoxing_chromium_manager.progress_tracker,
            task_id=container.chaoxing_chromium_manager.stream_task_id(),
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _to_chaoxing_chromium_response(status) -> ChaoxingChromiumResponse:
    return ChaoxingChromiumResponse(
        key=status.key,
        label=status.label,
        local_path=status.local_path,
        purpose=status.purpose,
        downloaded=status.downloaded,
        status=status.status,
        progress=status.progress,
        detail=status.detail,
        error=status.error,
    )
