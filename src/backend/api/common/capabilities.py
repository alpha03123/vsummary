"""Non-authoritative product capability endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.di.container import ApiContainerDep
from backend.core.capabilities import CapabilitySet


router = APIRouter()


@router.get("/api/capabilities")
def get_capabilities(container: ApiContainerDep) -> dict[str, bool]:
    capabilities = getattr(container, "capabilities", CapabilitySet())
    return capabilities.to_dict()
