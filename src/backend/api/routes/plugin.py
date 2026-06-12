from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.container import ApiContainerDep
from backend.api.contracts import GenerateBilibiliPluginSummaryRequest
from backend.api.responses import BilibiliPluginSummaryResponse
from backend.api.sse import stream_progress_events
from backend.video_summary.composition.video_summary_runtime import AsrModelNotReadyError
from backend.video_summary.adapters.plugin.bilibili.models import BilibiliPluginVideoKey

router = APIRouter()


@router.post("/api/plugin/bilibili/summaries", response_model=BilibiliPluginSummaryResponse)
async def generate_bilibili_plugin_summary(
    request: GenerateBilibiliPluginSummaryRequest,
    container: ApiContainerDep,
) -> BilibiliPluginSummaryResponse:
    try:
        result = await container.generate_bilibili_plugin_summary.run(
            url=request.url,
            transcript_enhancement_enabled=request.transcript_enhancement_enabled,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AsrModelNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return BilibiliPluginSummaryResponse.from_model(result)


@router.get("/api/plugin/bilibili/summaries/{bvid}/pages/{page}", response_model=BilibiliPluginSummaryResponse)
def get_bilibili_plugin_summary(
    bvid: str,
    page: int,
    container: ApiContainerDep,
) -> BilibiliPluginSummaryResponse:
    result = container.generate_bilibili_plugin_summary.get_summary(bvid=bvid, page=page)
    if result is None:
        raise HTTPException(status_code=404, detail=f"summary not found for Bilibili video '{bvid}/p{page}'")
    return BilibiliPluginSummaryResponse.from_model(result)


@router.get("/api/plugin/bilibili/tasks/{bvid}/pages/{page}/progress")
async def stream_bilibili_plugin_progress(
    bvid: str,
    page: int,
    container: ApiContainerDep,
) -> StreamingResponse:
    task_id = BilibiliPluginVideoKey(bvid=bvid, page=page).task_id
    return StreamingResponse(
        stream_progress_events(
            tracker=container.plugin_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/api/plugin/bilibili/tasks/{bvid}/pages/{page}/cancel")
def cancel_bilibili_plugin_summary(
    bvid: str,
    page: int,
    container: ApiContainerDep,
) -> dict[str, str]:
    task_id = BilibiliPluginVideoKey(bvid=bvid, page=page).task_id
    container.plugin_progress_tracker.request_cancel(task_id)
    return {"status": "cancelling", "task_id": task_id}
