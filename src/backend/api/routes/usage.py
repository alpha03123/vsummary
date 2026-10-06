"""Authenticated, product-neutral LLM usage statistics."""

from datetime import timezone
from fastapi import APIRouter, Depends, HTTPException
from backend.api.di.container import ApiContainerDep
from backend.api.dependencies import get_workspace_context
from backend.core.context import WorkspaceContext
from backend.api.schemas.contracts import (
    ProviderUsageCategoryResponse,
    ProviderUsageProviderResponse,
    ProviderUsageRecordResponse,
    ProviderUsageResponse,
    ProviderUsageTimelineBucketResponse,
    ProviderUsageTotalsResponse,
)

router = APIRouter()


@router.get("/api/provider-settings/usage", response_model=ProviderUsageResponse)
def get_provider_usage(
    container: ApiContainerDep, context: WorkspaceContext = Depends(get_workspace_context),
    range: str = "7d",
) -> ProviderUsageResponse:
    """GET /api/provider-settings/usage — 获取当前 workspace 内当前账号的 LLM token 用量统计。"""
    try:
        summary = container.usage_store.summarize(
            range_key=range, workspace_id=context.workspace_id, actor_id=context.actor_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return ProviderUsageResponse(
        range=summary.range_key,
        total=ProviderUsageTotalsResponse(
            prompt_tokens=summary.total.prompt_tokens,
            completion_tokens=summary.total.completion_tokens,
            total_tokens=summary.total.total_tokens,
        ),
        by_category=[
            ProviderUsageCategoryResponse(
                category=item.category,
                prompt_tokens=item.prompt_tokens,
                completion_tokens=item.completion_tokens,
                total_tokens=item.total_tokens,
            )
            for item in summary.by_category
        ],
        by_provider=[
            ProviderUsageProviderResponse(
                provider=item.provider,
                base_url=item.base_url,
                model=item.model,
                prompt_tokens=item.prompt_tokens,
                completion_tokens=item.completion_tokens,
                total_tokens=item.total_tokens,
            )
            for item in summary.by_provider
        ],
        recent=[
            ProviderUsageRecordResponse(
                created_at=item.created_at.replace(tzinfo=timezone.utc).isoformat(),
                category=item.category,
                provider=item.provider,
                base_url=item.base_url,
                model=item.model,
                prompt_tokens=item.prompt_tokens,
                completion_tokens=item.completion_tokens,
                total_tokens=item.total_tokens,
            )
            for item in summary.recent
        ],
        timeline_granularity=summary.timeline_granularity,
        timeline=[
            ProviderUsageTimelineBucketResponse(
                started_at=item.started_at.isoformat(),
                generation_tokens=item.generation_tokens,
                chat_tokens=item.chat_tokens,
                total_tokens=item.total_tokens,
            )
            for item in summary.timeline
        ],
    )


