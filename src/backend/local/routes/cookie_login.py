"""Desktop browser cookie initialization routes for Local only."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.dependencies import WorkspaceServicesDep
from backend.bilibili.ytdlp_bilibili import BilibiliCookieInitError


router = APIRouter()


class CookieStatusResponse(BaseModel):
    configured: bool


@router.post("/api/linked/bilibili/cookie/init", response_model=CookieStatusResponse)
async def init_bilibili_cookie(services: WorkspaceServicesDep) -> CookieStatusResponse:
    try:
        configured = await asyncio.to_thread(services.bilibili_cookie_initializer.init)
    except (BilibiliCookieInitError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return CookieStatusResponse(configured=configured)


@router.post("/api/linked/{provider}/cookie/init", response_model=CookieStatusResponse)
async def init_external_cookie(provider: str, services: WorkspaceServicesDep) -> CookieStatusResponse:
    initializer = services.external_cookie_initializers.get(provider.lower())
    if initializer is None:
        raise HTTPException(status_code=404, detail=f"unsupported external provider '{provider}'")
    try:
        configured = await asyncio.to_thread(initializer.init)
    except Exception as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return CookieStatusResponse(configured=configured)
