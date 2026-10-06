from fastapi import APIRouter, Depends, HTTPException
from backend.api.di.container import ApiContainerDep
from backend.api.dependencies import get_workspace_context
from backend.core.context import WorkspaceContext

router = APIRouter()


@router.get('/api/chat-requests/{request_id}')
def chat_request(request_id: str, host: ApiContainerDep, context: WorkspaceContext = Depends(get_workspace_context)):
    state = host.chat_queue.get(context, request_id) if host.chat_queue is not None else None
    if state is None:
        raise HTTPException(status_code=404, detail='Chat request not found.')
    return state


@router.post('/api/chat-requests/{request_id}/cancel')
def cancel_chat_request(request_id: str, host: ApiContainerDep, context: WorkspaceContext = Depends(get_workspace_context)):
    chat_request(request_id, host, context)
    host.chat_queue.cancel(context, request_id)
    return chat_request(request_id, host, context)
