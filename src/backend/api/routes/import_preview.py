from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from backend.api.dependencies import WorkspaceServicesDep, get_workspace_context
from backend.core.context import WorkspaceContext
from backend.video_summary.infrastructure.import_preview import ImportPreviewStore
from backend.api.schemas.responses import SeriesResponse

router=APIRouter()

class LinkedPreviewRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    provider:str
    url:str

class ImportSelectionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    selected_video_ids:list[str]

def preview_store(services,context):
    return ImportPreviewStore(services.linked_series_workspace.cache_root/'import-previews',context)

@router.post('/api/import/linked/preview')
async def preview_linked(data:LinkedPreviewRequest,services:WorkspaceServicesDep,context:WorkspaceContext=Depends(get_workspace_context)):
    try:
        series=await services.resolve_linked_series.preview(provider=data.provider,url=data.url)
        items=[{'id':video.video_id,'title':video.title,'duration_seconds':video.duration_seconds} for video in series.videos]
        return preview_store(services,context).create('linked',series.title,items,linked=series)
    except ValueError as error:raise HTTPException(422,str(error)) from error
    except RuntimeError as error:raise HTTPException(502,str(error)) from error

@router.post('/api/import/linked/{token}/commit')
def commit_linked(token:str,data:ImportSelectionRequest,services:WorkspaceServicesDep,context:WorkspaceContext=Depends(get_workspace_context)):
    store=preview_store(services,context)
    try:
        with store.locked(token) as plan:
            linked=store.linked(plan,data.selected_video_ids)
            result=services.resolve_linked_series.commit(linked)
        store.discard(token)
        return SeriesResponse.from_model(result)
    except ValueError as error:raise HTTPException(422,str(error)) from error
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except PermissionError as error:raise HTTPException(403,str(error)) from error

@router.delete('/api/import/previews/{token}')
def discard_preview(token:str,services:WorkspaceServicesDep,context:WorkspaceContext=Depends(get_workspace_context)):
    try:preview_store(services,context).discard(token)
    except LookupError:return {'discarded':True}
    except PermissionError as error:raise HTTPException(403,str(error)) from error
    return {'discarded':True}
