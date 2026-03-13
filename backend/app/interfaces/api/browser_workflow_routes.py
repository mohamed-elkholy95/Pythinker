"""Browser workflow SSE streaming routes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.domain.models.user import User
from app.interfaces.dependencies import get_browser_workflow_service, get_current_user

if TYPE_CHECKING:
    from app.application.services.browser_workflow_service import BrowserWorkflowService

router = APIRouter(prefix="/browser-workflow", tags=["browser-workflow"])


@router.get("/capabilities")
async def get_capabilities(
    current_user: User = Depends(get_current_user),
    workflow_service: BrowserWorkflowService = Depends(get_browser_workflow_service),
):
    """Get browser workflow capabilities."""
    _ = current_user
    return await workflow_service.get_capabilities()


@router.get("/fetch/stream")
async def fetch_stream(
    request: Request,
    url: str,
    mode: str = "dynamic",
    current_user: User = Depends(get_current_user),
    workflow_service: BrowserWorkflowService = Depends(get_browser_workflow_service),
):
    """SSE stream of browser fetch workflow progress."""
    _ = current_user

    async def event_generator():
        async for event in workflow_service.fetch_with_progress(url, mode):
            if await request.is_disconnected():
                return
            yield {
                "data": json.dumps(event),
                "event": "progress",
                "id": str(event.get("event_id", "")),
                "retry": 15000,
            }

    return EventSourceResponse(
        event_generator(),
        send_timeout=30,
        headers={"Cache-Control": "no-cache"},
    )


@router.delete("/cache")
async def invalidate_cache(
    url: str | None = None,
    current_user: User = Depends(get_current_user),
    workflow_service: BrowserWorkflowService = Depends(get_browser_workflow_service),
):
    """Invalidate browser workflow cache entries."""
    _ = current_user
    count = await workflow_service.invalidate_cache(url)
    return {"invalidated": count}
