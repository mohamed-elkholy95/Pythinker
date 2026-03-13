"""Browser workflow SSE streaming routes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse

from app.domain.external.stealth_types import StealthMode
from app.domain.models.user import User
from app.domain.utils.url_filters import is_ssrf_target
from app.interfaces.dependencies import get_browser_workflow_service, get_current_user

if TYPE_CHECKING:
    from app.application.services.browser_workflow_service import BrowserWorkflowService

router = APIRouter(prefix="/browser-workflow", tags=["browser-workflow"])


def _validate_public_url(url: str) -> str:
    """Validate browser workflow URLs with the shared SSRF guard."""
    reason = is_ssrf_target(url)
    if reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    return url


@router.get("/capabilities")
async def get_capabilities(
    current_user: User = Depends(get_current_user),
    workflow_service: BrowserWorkflowService = Depends(get_browser_workflow_service),
) -> dict[str, Any]:
    """Get browser workflow capabilities."""
    _ = current_user
    return await workflow_service.get_capabilities()


@router.get("/fetch/stream")
async def fetch_stream(
    request: Request,
    url: str,
    mode: StealthMode = StealthMode.DYNAMIC,
    current_user: User = Depends(get_current_user),
    workflow_service: BrowserWorkflowService = Depends(get_browser_workflow_service),
) -> EventSourceResponse:
    """SSE stream of browser fetch workflow progress."""
    _ = current_user
    validated_url = _validate_public_url(url)

    async def event_generator():
        async for event in workflow_service.fetch_with_progress(validated_url, mode):
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
) -> dict[str, int]:
    """Invalidate browser workflow cache entries."""
    _ = current_user
    validated_url = _validate_public_url(url) if url else None
    count = await workflow_service.invalidate_cache(validated_url)
    return {"invalidated": count}
